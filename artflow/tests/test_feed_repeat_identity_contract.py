"""Identity-role acceptance contracts, never a claim of visual face fidelity.

Repository/accounting fakes are shared; real handlers, image_service and Nexus
HTTP serialization run against synthetic URLs and an in-memory MockTransport.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from api import image_service, miniapp_routes, neironych_image_adapter, nexus_image_adapter
from api.nexusapi_client import NexusApiClient
from api.repeat_runtime import current_repeat_launch_context
from bot.handlers import feed, image_gen, repeat_safe
from bot.utils import feed_media
from core import feed_remix_prompt as prompt_core
from db import repository as repo
from db.models import ImageGenerationAction
from tests import test_nano_banana_pro_reference_transport as reference_fixtures
from tests.test_nano_banana_pro_reference_transport import (
    REFS,
    SECRET,
    SOURCE,
    mutable_state,
)

local_launch = reference_fixtures.local_launch
MODELS = ["nano-banana-pro", "nano-banana-2"]
OTHER_SOURCE = "https://example.test/other-public-scene.jpg"
OWN_RECIPE = "My visible recipe: watercolor street portrait"
IDENTITY_RULE = (
    "The supplied reference photos are the EXCLUSIVE source of the subject's face and identity. "
    "Do not copy the original subject's face. Use the clearest frontal view of the reader."
)
SUFFIX = "\n\nПальто синее 🧥\n\nKeep this line.  \n\t"


@pytest.mark.parametrize("surface", ["web", "miniapp"])
@pytest.mark.parametrize("provider", ["neironych", "nexus"])
async def test_feed_recipe_http_502_refunds_without_second_post(
    local_launch, wire, monkeypatch, surface, provider,
):
    from core.provider_routing import ProviderRoute
    from db.models import GenerationStatus

    launch = local_launch
    launch.generation.model = "nano-banana-2.1"
    launch.source.input_params = {"hidden_prompt": False}
    monkeypatch.setattr(
        miniapp_routes, "get_nano21_route",
        AsyncMock(return_value=ProviderRoute("nano-banana-2.1", provider, "database")),
    )
    calls = []
    async def provider_error(*args, **kwargs):
        calls.append(kwargs["request_id"])
        assert kwargs["image_url"] == REFS[0]
        if provider == "nexus":
            raise nexus_image_adapter.NexusImageSubmissionUnknown(
                "HTTP 502", status_code=502, idempotency_key=kwargs["request_id"],
            )
        raise neironych_image_adapter.NeironychImageError(
            "HTTP 502", status_code=502, request_id=kwargs["request_id"],
        )
    monkeypatch.setattr(miniapp_routes.image_service, "generate_image", provider_error)
    async def refund(session, gen_id, error, **kwargs):
        assert gen_id == launch.generation.id
        task = (
            neironych_image_adapter.encode_task_id(calls[0])
            if provider == "neironych"
            else nexus_image_adapter.encode_submission_id(calls[0])
        )
        assert kwargs["expected_task_id"] == miniapp_routes.task_id_for_surface(task, surface)
        launch.generation.status = GenerationStatus.failed
        return True, 4.0
    settlement = AsyncMock(side_effect=refund)
    monkeypatch.setattr(repo, "fail_generation_and_refund", settlement)

    result = await miniapp_routes.remix_feed_post(
        77,
        miniapp_routes.FeedRemixRequest(model="nano-banana-2.1", image_url=REFS[0]),
        session=launch.session, user=launch.user, surface=surface,
    )
    assert result.status == "failed"
    assert len(calls) == 1
    assert settlement.await_args.kwargs["refund_note"] == f"image:http_5xx:{provider}"
    repo.increment_feed_share.assert_not_awaited()


@pytest.mark.parametrize("surface", ["web", "miniapp"])
async def test_feed_recipe_nexus_pro_502_uses_atomic_refund(
    local_launch, wire, monkeypatch, surface,
):
    from db.models import GenerationStatus

    launch = local_launch
    launch.generation.model = "nano-banana-pro"
    launch.source.input_params = {"hidden_prompt": False}
    async def provider_error(*args, **kwargs):
        assert kwargs["request_id"] is None
        raise nexus_image_adapter.NexusApiError("HTTP 502", status_code=502)
    monkeypatch.setattr(miniapp_routes.image_service, "generate_image", provider_error)
    async def refund(session, gen_id, error, **kwargs):
        assert kwargs["require_missing_task_id"] is True
        launch.generation.status = GenerationStatus.failed
        return True, 4.0
    settlement = AsyncMock(side_effect=refund)
    monkeypatch.setattr(repo, "fail_generation_and_refund", settlement)

    result = await miniapp_routes.remix_feed_post(
        77, miniapp_routes.FeedRemixRequest(model="nano-banana-pro", image_url=REFS[0]),
        session=launch.session, user=launch.user, surface=surface,
    )
    assert result.status == "failed"
    settlement.assert_awaited_once()
    repo.increment_feed_share.assert_not_awaited()


@pytest.mark.parametrize("surface", ["web", "miniapp"])
async def test_feed_5xx_lost_guard_keeps_accepted_share(
    local_launch, wire, monkeypatch, surface,
):
    from db.models import GenerationStatus

    launch = local_launch
    launch.generation.model = "nano-banana-pro"
    launch.generation.status = GenerationStatus.done
    launch.source.input_params = {"hidden_prompt": False}
    monkeypatch.setattr(
        miniapp_routes.image_service, "generate_image",
        AsyncMock(side_effect=nexus_image_adapter.NexusApiError("HTTP 502", status_code=502)),
    )
    monkeypatch.setattr(repo, "fail_generation_and_refund", AsyncMock(return_value=(False, 0.0)))

    result = await miniapp_routes.remix_feed_post(
        77, miniapp_routes.FeedRemixRequest(model="nano-banana-pro", image_url=REFS[0]),
        session=launch.session, user=launch.user, surface=surface,
    )
    assert result.status == "done"
    repo.increment_feed_share.assert_awaited_once()


@pytest.fixture
async def wire(monkeypatch):
    posts = []

    def capture(request):
        assert request.method == "POST"
        assert str(request.url) == "https://nexus.test/generate"
        posts.append({"body": json.loads(request.content), "key": request.headers["Idempotency-Key"]})
        return httpx.Response(200, json={"task_id": f"synthetic-{len(posts)}", "status": "pending"})

    async with httpx.AsyncClient(
        base_url="https://nexus.test", transport=httpx.MockTransport(capture),
    ) as http:
        client = NexusApiClient(api_key="synthetic-test-only", base_url="https://nexus.test", client=http)
        monkeypatch.setattr(nexus_image_adapter, "NexusApiClient", lambda: client)
        for module, method in [
            (image_service.kieai_client, "create_task"),
            (image_service.comet_fallback, "generate_image"),
            (image_service.neironych_image_adapter, "generate_nano_banana21_image"),
        ]:
            monkeypatch.setattr(module, method, AsyncMock(side_effect=AssertionError("No external provider calls")))
        yield posts


def assert_identity_roles(prompt):
    assert "EXCLUSIVE source" in prompt
    assert "user's face and identity" in prompt
    assert "final image is public scene reference only" in prompt
    assert "Do not copy, retain, average or blend the author's face" in prompt
    assert "user's identity takes priority" in prompt
    assert SECRET not in prompt


def assert_face_replacement(prompt):
    assert_identity_roles(prompt)
    assert "Edit the final public scene image" in prompt
    assert "replace the source subject's face" in prompt
    assert "preserve the scene composition" in prompt
    assert "collage or multiple views" in prompt
    assert "new pose, framing and composition" not in prompt


def assert_scene_first_edit(prompt):
    # This was the working Nexus photo-repeat prompt before the Oct-13 reversal.
    assert prompt.startswith(prompt_core._LEGACY_SOURCE_FIRST_PROMPT)
    assert "The source is the first image" in prompt
    assert "Use additional references for the user's appearance" in prompt
    assert "The source is the final image" not in prompt
    assert "Edit the final public scene image" not in prompt
    assert SECRET not in prompt


def assert_recipe_identity_priority(prompt, creator_prompt):
    assert creator_prompt in prompt
    assert prompt.count(creator_prompt) == 1
    assert "sole source of the person's face" in prompt
    assert "hair color" in prompt
    assert "largest clear frontal face" in prompt
    assert "takes priority over conflicting" in prompt
    assert prompt.endswith("never the original creator's subject.")


def previous_generation(prompt, *, version=2, **extra):
    context = {"version": version, "source_generation_id": 77, "prompt": prompt}
    return SimpleNamespace(
        id=88, user_id=42, source_feed_gen_id=77, prompt=prompt,
        input_params={prompt_core.FEED_REMIX_CONTEXT_KEY: context}, **extra,
    )


@pytest.mark.parametrize("surface", ["web", "miniapp"])
async def test_collage_edit_uses_creator_prompt_and_only_reader_reference(
    local_launch, wire, surface,
):
    # Regression: real task 59011 had a multi-angle user collage, an author
    # portrait as the final reference and an output dominated by the author.
    # No paid requests: the Nexus transport is a synthetic MockTransport.
    await miniapp_routes.remix_feed_post(
        77,
        miniapp_routes.FeedRemixRequest(
            model="nano-banana-pro", image_url=REFS[0], mode="image", quality="2K",
        ),
        session=local_launch.session, user=local_launch.user, surface=surface,
    )
    params = wire[0]["body"]["params"]
    assert params["image_urls"] == [REFS[0]]
    prompt = params["prompt"]
    assert prompt == SECRET


def test_recipe_context_is_owner_bound_digest_only_and_respects_rollout_rollback():
    submitted = "Original unpublished creator recipe with lens and pose.\n\nUse my portrait."
    ctx = prompt_core.feed_image_recipe_context(77, submitted)
    assert ctx["version"] == prompt_core.FEED_IMAGE_RECIPE_CONTEXT_VERSION
    assert "prompt" not in ctx
    previous = SimpleNamespace(
        user_id=42, source_feed_gen_id=77, prompt=submitted,
        input_params={prompt_core.FEED_REMIX_CONTEXT_KEY: ctx},
    )
    assert prompt_core.trusted_feed_image_recipe_prompt(
        previous, user_id=42, source_generation_id=77,
    ) == submitted
    assert prompt_core.trusted_feed_image_prompt(
        previous, user_id=42, source_generation_id=77,
        has_user_references=True, scene_first=True,
    ) is None  # Feature rollback cannot resurrect the private recipe.
    assert prompt_core.trusted_feed_prompt(
        previous, user_id=42, source_generation_id=77,
    ) is None  # A photo recipe cannot be migrated into the video prompt path.
    assert prompt_core.trusted_feed_image_recipe_prompt(
        previous, user_id=99, source_generation_id=77,
    ) is None
    assert prompt_core.trusted_feed_image_recipe_prompt(
        previous, user_id=42, source_generation_id=78,
    ) is None
    previous.prompt += " tampered"
    assert prompt_core.trusted_feed_image_recipe_prompt(
        previous, user_id=42, source_generation_id=77,
    ) is None


def test_creator_recipe_is_verbatim_and_old_policy_can_be_unwrapped():
    creator = "Gothic black-and-white portrait of a witch with dark hair."
    composed = prompt_core.build_feed_image_recipe_prompt(creator)
    assert composed == creator
    assert prompt_core.build_feed_image_recipe_prompt(
        composed, previous_instruction=IDENTITY_RULE,
    ) == composed
    edited = prompt_core.build_feed_image_recipe_prompt(
        composed, "blue cloak", previous_instruction=IDENTITY_RULE,
    )
    assert edited == creator + "\n\nИзменения, которые запросил пользователь для повтора: blue cloak"
    new_rule = "Use the reader's facial identity, never the creator's facial identity."
    updated = prompt_core.build_feed_image_recipe_prompt(
        composed, previous_instruction=IDENTITY_RULE,
    )
    assert updated == creator
    old_wrapped = (
        prompt_core._IMAGE_RECIPE_RELATIONSHIP_PREFIX
        + "Creator scene prompt:\n" + creator
        + "\n\nSubject identity policy:\n" + IDENTITY_RULE
    )
    previous = SimpleNamespace(
        user_id=42, source_feed_gen_id=77, prompt=old_wrapped,
        input_params={prompt_core.FEED_REMIX_CONTEXT_KEY: prompt_core.feed_image_recipe_context(
            77, old_wrapped, IDENTITY_RULE,
        )},
    )
    assert prompt_core.trusted_feed_image_recipe_instruction(
        previous, user_id=42, source_generation_id=77,
    ) == IDENTITY_RULE
    assert prompt_core.build_feed_image_recipe_prompt(
        old_wrapped, previous_instruction=IDENTITY_RULE,
    ) == creator
    previous.input_params[prompt_core.FEED_REMIX_CONTEXT_KEY]["identity_instruction"] = new_rule
    assert prompt_core.trusted_feed_image_recipe_instruction(
        previous, user_id=42, source_generation_id=77,
    ) is None


def test_october_first_recipe_uses_exact_creator_prompt_without_identity_policy():
    creator = "Studio portrait, angular jawline, full lips, white blazer."
    assert prompt_core.build_feed_image_recipe_prompt(creator) == creator


def test_creator_face_descriptions_remain_verbatim_without_added_rule():
    creator = "Studio portrait, angular jawline, full lips, white blazer."
    composed = prompt_core.build_feed_image_recipe_prompt(creator)
    assert composed == creator
    assert prompt_core.build_feed_image_recipe_prompt(
        composed, previous_instruction=IDENTITY_RULE,
    ) == creator


def test_recipe_continuation_replaces_old_unlabeled_identity_rule():
    creator = "Black-and-white portrait of a witch."
    old_rule = "Use the old user's face from uploaded photo."
    previous = creator + "\n\n" + old_rule
    saved = SimpleNamespace(
        user_id=42, source_feed_gen_id=77, prompt=previous,
        input_params={prompt_core.FEED_REMIX_CONTEXT_KEY: prompt_core.feed_image_recipe_context(
            77, previous, old_rule,
        )},
    )
    assert prompt_core.trusted_feed_image_recipe_instruction(
        saved, user_id=42, source_generation_id=77,
    ) == old_rule
    continued = prompt_core.build_feed_image_recipe_prompt(
        previous, "blue cloak", previous_instruction=old_rule,
    )
    assert continued == creator + "\n\nИзменения, которые запросил пользователь для повтора: blue cloak"


def test_recipe_prompt_does_not_add_identity_instruction():
    composed = prompt_core.build_feed_image_recipe_prompt("Candlelit studio scene.")
    assert composed == "Candlelit studio scene."


def test_recipe_continuation_unwraps_previous_main_policy_wording():
    creator = "Gothic forest portrait."
    previous = (
        prompt_core._IMAGE_RECIPE_SCENE_PREFIX + creator
        + "\n\nReference identity priority: Previous policy wording."
    )
    continued = prompt_core.build_feed_image_recipe_prompt(previous, "silver bat crown")
    assert continued.count(creator) == 1
    assert "Previous policy wording" not in continued
    assert IDENTITY_RULE not in continued
    assert continued == creator + "\n\nИзменения, которые запросил пользователь для повтора: silver bat crown"


def test_recipe_continuation_unwraps_previous_double_policy_once():
    creator = "Gothic forest portrait."
    old_rule = "Use the previous reader policy."
    previous = (
        "Subject identity policy:\n" + old_rule
        + "\n\nCreator scene prompt:\n" + creator
        + "\n\nSubject identity policy:\n" + old_rule
    )
    continued = prompt_core.build_feed_image_recipe_prompt(
        previous, previous_instruction=old_rule,
    )
    assert continued == creator


def test_recipe_continuation_keeps_creator_scene_once():
    creator = "Candlelit portrait, red velvet clothing."
    first = prompt_core.build_feed_image_recipe_prompt(creator)
    continued = prompt_core.build_feed_image_recipe_prompt(
        first, "blue cloak", previous_instruction=IDENTITY_RULE,
    )
    assert continued == creator + "\n\nИзменения, которые запросил пользователь для повтора: blue cloak"


def test_public_derived_recipe_is_available_to_its_owner_for_all_image_models():
    source = SimpleNamespace(
        id=77, user_id=42, is_public_feed=True, gen_type="image",
        source_feed_gen_id=55, prompt="Server-held derived edit",
    )
    assert prompt_core.feed_image_original_recipe_allowed(
        source, user_id=42, model_key="nano-banana-2.1", enabled=True,
    )
    assert prompt_core.feed_image_original_recipe_allowed(
        source, user_id=42, model_key="nano-banana-2", enabled=True,
    )



@pytest.mark.parametrize("surface", ["web", "miniapp"])
@pytest.mark.parametrize("model", MODELS)
async def test_ksu_style_feed_recipe_replaces_author_refs_and_preserves_settings(
    local_launch, wire, monkeypatch, model, surface,
):
    monkeypatch.setattr(miniapp_routes.settings, "FEED_ORIGINAL_RECIPE_ENABLED", True)
    source = local_launch.source
    source.source_feed_gen_id = None
    source.input_params = {
        "hidden_prompt": False,
        "reference_images": [SOURCE],
        "img_ratio": "2:3",
        "img_quality": "2K",
    }
    source.prompt = (
        "Original creator recipe: studio lighting, detailed wardrobe, winter scenery, "
        "camera angle and film aesthetics."
    )
    source.model = "nano-banana-2"
    result = await miniapp_routes.remix_feed_post(
        77,
        miniapp_routes.FeedRemixRequest(model=model, image_url=REFS[0], mode="image"),
        session=local_launch.session, user=local_launch.user, surface=surface,
    )
    params = wire[0]["body"]["params"]
    assert params["image_urls"] == [REFS[0]]  # Author output and original input excluded.
    assert source.prompt in params["prompt"]
    assert params["prompt"] == source.prompt
    assert params["aspect_ratio"] == "2:3"
    assert params["image_size"] == "2K"
    args = repo.create_generation.await_args
    assert args.kwargs["source_feed_gen_id"] == 77
    context = args.kwargs["input_params"][prompt_core.FEED_REMIX_CONTEXT_KEY]
    assert context["version"] == 4
    assert "source_image_url" not in context
    assert local_launch.created_sessions[-1].base_prompt is None
    assert result.prompt_hidden is True
    assert source.prompt not in str(result)


async def test_monochrome_recipe_sends_exact_creator_prompt_and_reader_photo(
    local_launch, wire, monkeypatch,
):
    monkeypatch.setattr(miniapp_routes.settings, "FEED_ORIGINAL_RECIPE_ENABLED", True)
    source = local_launch.source
    source.source_feed_gen_id = None
    source.input_params = {"reference_images": [SOURCE], "img_ratio": "9:16"}
    source.prompt = "Black-and-white portrait of a black-haired witch with a silver bat crown."

    await miniapp_routes.remix_feed_post(
        77,
        miniapp_routes.FeedRemixRequest(model="nano-banana-pro", image_url=REFS[0]),
        session=local_launch.session, user=local_launch.user,
    )

    submitted = wire[0]["body"]["params"]
    assert submitted["image_urls"] == [REFS[0]]
    prompt = submitted["prompt"]
    assert source.prompt in prompt
    assert IDENTITY_RULE not in prompt
    assert SOURCE not in submitted["image_urls"]
    saved = repo.create_generation.await_args.args[4]
    assert saved == prompt
    context = repo.create_generation.await_args.kwargs["input_params"][prompt_core.FEED_REMIX_CONTEXT_KEY]
    owned_repeat = SimpleNamespace(
        user_id=local_launch.user.id, source_feed_gen_id=77, prompt=saved,
        input_params={prompt_core.FEED_REMIX_CONTEXT_KEY: context},
    )
    assert prompt_core.trusted_feed_image_recipe_prompt(
        owned_repeat, user_id=local_launch.user.id, source_generation_id=77,
    ) == prompt


@pytest.mark.parametrize("model", ["nano-banana-pro", "nano-banana-2"])
@pytest.mark.parametrize("surface", ["web", "miniapp"])
async def test_every_nexus_image_model_uses_creator_prompt_and_reader_photo_without_source_metadata(
    local_launch, wire, model, surface,
):
    # Old public posts may not have input_params at all. The reader collage is
    # the only provider image; neither the finished image nor creator refs go.
    local_launch.source.input_params = None
    await miniapp_routes.remix_feed_post(
        77, miniapp_routes.FeedRemixRequest(model=model, image_url=REFS[0]),
        session=local_launch.session, user=local_launch.user, surface=surface,
    )
    submitted = wire[0]["body"]["params"]
    assert submitted["image_urls"] == [REFS[0]]
    assert submitted["prompt"] == SECRET
    context = repo.create_generation.await_args.kwargs["input_params"][prompt_core.FEED_REMIX_CONTEXT_KEY]
    assert context["version"] == 4


@pytest.mark.parametrize("model", ["nano-banana-pro", "nano-banana-2"])
async def test_derived_photo_on_other_image_models_uses_public_origin_recipe(
    local_launch, wire, model,
):
    local_launch.source.source_feed_gen_id = 55
    local_launch.source.input_params = {"reference_images": [SOURCE]}
    origin = SimpleNamespace(**{**vars(local_launch.source), "id": 55, "source_feed_gen_id": None,
                                "prompt": "Original creator scene recipe."})
    repo.get_public_feed_generation.side_effect = lambda _session, source_id: (
        local_launch.source if source_id == 77 else origin if source_id == 55 else None
    )
    await miniapp_routes.remix_feed_post(
        77, miniapp_routes.FeedRemixRequest(model=model, image_url=REFS[0]),
        session=local_launch.session, user=local_launch.user,
    )
    submitted = wire[0]["body"]["params"]
    assert submitted["image_urls"] == [REFS[0]]
    assert submitted["prompt"] == origin.prompt


@pytest.mark.parametrize("model", ["nano-banana-pro", "google/nano-banana", "midjourney-blend"])
async def test_photo_repeat_without_usable_reader_prompt_and_image_contract_fails_before_charge(
    local_launch, wire, model,
):
    request = miniapp_routes.FeedRemixRequest(
        model=model, image_url=REFS[0] if model != "nano-banana-pro" else None,
    )
    with pytest.raises(HTTPException) as error:
        await miniapp_routes.remix_feed_post(
            77, request, session=local_launch.session, user=local_launch.user,
        )
    assert error.value.status_code == 422
    repo.charge_image_generation.assert_not_awaited()
    assert wire == []


@pytest.mark.parametrize("enabled", [False, True])
async def test_disabled_recipe_fails_closed_without_author_photo(
    local_launch, wire, monkeypatch, enabled,
):
    monkeypatch.setattr(miniapp_routes.settings, "FEED_ORIGINAL_RECIPE_ENABLED", enabled)
    local_launch.source.input_params = {"reference_images": [SOURCE]}
    if not enabled:
        with pytest.raises(HTTPException) as error:
            await miniapp_routes.remix_feed_post(
                77, miniapp_routes.FeedRemixRequest(model="nano-banana-pro", image_url=REFS[0]),
                session=local_launch.session, user=local_launch.user,
            )
        assert error.value.status_code == 422
        assert wire == []
        repo.charge_image_generation.assert_not_awaited()
    else:
        await miniapp_routes.remix_feed_post(
            77, miniapp_routes.FeedRemixRequest(model="nano-banana-pro", image_url=REFS[0]),
            session=local_launch.session, user=local_launch.user,
        )
        params = wire[0]["body"]["params"]
        assert params["image_urls"] == [REFS[0]]
        assert params["prompt"] == SECRET


async def test_hidden_creator_prompt_used_by_provider_not_exposed_in_client_response(
    local_launch, wire, monkeypatch,
):
    monkeypatch.setattr(miniapp_routes.settings, "FEED_ORIGINAL_RECIPE_ENABLED", True)
    local_launch.source.input_params = {"hidden_prompt": True, "reference_images": [SOURCE]}
    result = await miniapp_routes.remix_feed_post(
        77, miniapp_routes.FeedRemixRequest(model="nano-banana-pro", image_url=REFS[0]),
        session=local_launch.session, user=local_launch.user,
    )
    assert wire[0]["body"]["params"]["image_urls"] == [REFS[0]]
    assert wire[0]["body"]["params"]["prompt"] == SECRET
    assert SECRET not in str(result)
    assert result.prompt_hidden is True
    assert local_launch.created_sessions[-1].base_prompt is None
    ctx = repo.create_generation.await_args.kwargs["input_params"][prompt_core.FEED_REMIX_CONTEXT_KEY]
    assert ctx["version"] == 4 and "prompt" not in ctx




async def test_historic_recipe_missing_reference_count_fails_before_charge(
    local_launch, wire, monkeypatch,
):
    monkeypatch.setattr(miniapp_routes.settings, "FEED_ORIGINAL_RECIPE_ENABLED", True)
    local_launch.source.input_params = {
        "hidden_prompt": False, "reference_images": [SOURCE, OTHER_SOURCE],
    }
    with pytest.raises(HTTPException) as err:
        await miniapp_routes.remix_feed_post(
            77, miniapp_routes.FeedRemixRequest(model="nano-banana-pro", image_url=REFS[0]),
            session=local_launch.session, user=local_launch.user,
        )
    assert err.value.status_code == 422
    repo.charge_image_generation.assert_not_awaited()
    assert wire == []



async def test_telegram_replay_collector_does_not_reserve_creator_image_slot(
    local_launch, monkeypatch,
):
    from bot.handlers import repeat_reference_marketplace as composer
    source = local_launch.source
    source.input_params = {"hidden_prompt": True, "reference_images": [SOURCE]}
    source.source_feed_gen_id = None
    monkeypatch.setattr(composer.settings, "FEED_ORIGINAL_RECIPE_ENABLED", True)
    monkeypatch.setattr(composer.repo, "get_public_feed_generation", AsyncMock(return_value=source))
    state = {
        "feed_use_prompt": "server-side source prompt",
        "feed_use_gen_id": 77,
        "feed_use_user_id": local_launch.user.id,
        "feed_original_recipe_replay": True,
        "use_model_key": "nano-banana-pro",
    }
    candidate, cap, source_slots = await composer._reference_candidate(
        local_launch.session, state, reference_urls=[SOURCE, REFS[0]],
        file_ids=["synthetic-user-photo"],
    )
    assert candidate["reference_urls"] == [REFS[0]]
    assert candidate["ref_file_ids"] == ["synthetic-user-photo"]
    assert source_slots == 0
    assert cap == composer.repeat_references._repeat_max_refs("nano-banana-pro")
    assert composer.repeat_references._prompt_user_reference_limit("nano-banana-pro", state) == cap
    screen = composer._text({
        **state, "prompt_multi_ref_count": 1,
        "prompt_multi_ref_max": cap,
    })
    assert f"Референсы: <b>1/{cap}</b>" in screen
    assert "Повторим исходный рецепт автора" not in screen
    assert "Можно отправлять фото по одному" not in screen


async def test_quote_and_submission_inherit_identical_historic_photo_settings(
    local_launch, wire, monkeypatch,
):
    monkeypatch.setattr(miniapp_routes.settings, "FEED_ORIGINAL_RECIPE_ENABLED", True)
    local_launch.source.input_params = {
        "reference_images": [SOURCE], "img_ratio": "2:3", "img_quality": "2K",
    }
    body = miniapp_routes.FeedRemixRequest(model="nano-banana-pro", image_url=REFS[0])
    await miniapp_routes.quote_feed_remix(
        77, body, session=local_launch.session, user=local_launch.user,
    )
    from_quote = repo.resolve_image_model_cost.await_args.kwargs["quality"]
    await miniapp_routes.remix_feed_post(
        77, body, session=local_launch.session, user=local_launch.user,
    )
    assert from_quote == "2K"
    assert repo.resolve_image_model_cost.await_args.kwargs["quality"] == from_quote
    assert wire[0]["body"]["params"]["image_urls"] == [REFS[0]]
    assert wire[0]["body"]["params"]["aspect_ratio"] == "2:3"
    assert wire[0]["body"]["params"]["image_size"] == from_quote



@pytest.mark.parametrize("model", ["nano-banana-pro", "nano-banana-2"])
@pytest.mark.parametrize("surface", ["web", "miniapp"])
async def test_nexus_personalized_repeat_uses_reader_reference_only(
    local_launch, wire, model, surface,
):
    # Prod 59039 retained the author's face after source-last + face_replacement.
    # Prod 58493/58505 submitted the source image first with a concise edit
    # prompt to this same Nexus provider. Verify the actual provider body.
    await miniapp_routes.remix_feed_post(
        77,
        miniapp_routes.FeedRemixRequest(
            model=model, image_url=REFS[0], mode="image", quality="2K",
        ),
        session=local_launch.session, user=local_launch.user, surface=surface,
    )
    submitted = wire[0]["body"]["params"]
    assert submitted["image_urls"] == [REFS[0]]
    assert submitted["prompt"] == SECRET
    context = repo.create_generation.await_args.kwargs["input_params"][prompt_core.FEED_REMIX_CONTEXT_KEY]
    assert context["version"] == 4
    assert "source_image_url" not in context
    assert "prompt" not in context


@pytest.mark.parametrize("surface", ["web", "miniapp"])
async def test_nano21_derived_feed_uses_origin_prompt_and_only_reader_photo(
    local_launch, wire, monkeypatch, surface,
):
    local_launch.source.source_feed_gen_id = 55
    local_launch.source.input_params = {"reference_images": [SOURCE]}
    origin = SimpleNamespace(**{**vars(local_launch.source), "id": 55, "source_feed_gen_id": None,
                                "prompt": "Original author portrait recipe."})
    repo.get_public_feed_generation.side_effect = lambda _session, source_id: (
        local_launch.source if source_id == 77 else origin if source_id == 55 else None
    )
    generate = AsyncMock(return_value="https://example.test/generated.jpg")
    monkeypatch.setattr(image_service.neironych_image_adapter, "generate_nano_banana21_image", generate)
    monkeypatch.setattr(miniapp_routes, "get_nano21_route", AsyncMock(return_value=SimpleNamespace(primary_provider="neironych")))
    monkeypatch.setattr(repo, "finish_generation", AsyncMock(return_value=local_launch.generation))
    quote = await miniapp_routes.quote_feed_remix(
        77, miniapp_routes.FeedRemixRequest(model="nano-banana-2.1", image_url=REFS[0]),
        session=local_launch.session, user=local_launch.user,
    )
    await miniapp_routes.remix_feed_post(
        77, miniapp_routes.FeedRemixRequest(model="nano-banana-2.1", image_url=REFS[0]),
        session=local_launch.session, user=local_launch.user, surface=surface,
    )
    submitted = generate.await_args.kwargs
    assert quote["gen_type"] == "image"
    assert submitted["image_urls"] == [REFS[0]]
    assert submitted["prompt"] == origin.prompt
    assert SOURCE not in submitted["image_urls"]


@pytest.mark.parametrize("surface", ["web", "miniapp"])
async def test_nano21_derived_feed_missing_origin_fails_before_charge(local_launch, wire, surface):
    local_launch.source.source_feed_gen_id = 55
    repo.get_public_feed_generation.side_effect = lambda _session, source_id: (
        local_launch.source if source_id == 77 else None
    )
    with pytest.raises(HTTPException) as error:
        await miniapp_routes.remix_feed_post(
            77, miniapp_routes.FeedRemixRequest(model="nano-banana-2.1", image_url=REFS[0]),
            session=local_launch.session, user=local_launch.user, surface=surface,
        )
    assert error.value.status_code == 422
    assert wire == []
    repo.charge_image_generation.assert_not_awaited()


async def test_nano21_feed_repeat_without_reader_photo_fails_before_charge(local_launch, wire):
    with pytest.raises(HTTPException) as error:
        await miniapp_routes.remix_feed_post(
            77, miniapp_routes.FeedRemixRequest(model="nano-banana-2.1", image_url=SOURCE),
            session=local_launch.session, user=local_launch.user,
        )
    assert error.value.status_code == 422
    assert wire == []
    repo.charge_image_generation.assert_not_awaited()


async def test_nano21_disabled_recipe_fails_without_author_photo(local_launch, wire, monkeypatch):
    monkeypatch.setattr(miniapp_routes.settings, "FEED_ORIGINAL_RECIPE_ENABLED", False)
    with pytest.raises(HTTPException) as error:
        await miniapp_routes.remix_feed_post(
            77, miniapp_routes.FeedRemixRequest(model="nano-banana-2.1", image_url=REFS[0]),
            session=local_launch.session, user=local_launch.user,
        )
    assert error.value.status_code == 422
    assert wire == []
    repo.charge_image_generation.assert_not_awaited()


@pytest.mark.parametrize("surface", ["web", "miniapp"])
async def test_nano21_original_recipe_uses_exact_reader_reference(
    local_launch, wire, monkeypatch, surface,
):
    local_launch.source.source_feed_gen_id = None
    local_launch.source.input_params = {"reference_images": [SOURCE]}
    monkeypatch.setattr(miniapp_routes.settings, "FEED_ORIGINAL_RECIPE_ENABLED", True)
    generate = AsyncMock(return_value="https://example.test/generated.jpg")
    monkeypatch.setattr(image_service.neironych_image_adapter, "generate_nano_banana21_image", generate)
    monkeypatch.setattr(miniapp_routes, "get_nano21_route", AsyncMock(return_value=SimpleNamespace(primary_provider="neironych")))
    monkeypatch.setattr(repo, "finish_generation", AsyncMock(return_value=local_launch.generation))
    await miniapp_routes.remix_feed_post(
        77, miniapp_routes.FeedRemixRequest(model="nano-banana-2.1", image_url=REFS[0]),
        session=local_launch.session, user=local_launch.user, surface=surface,
    )
    submitted = generate.await_args.kwargs
    assert submitted["image_urls"] == [REFS[0]]
    assert SOURCE not in submitted["image_urls"]
    assert SECRET in submitted["prompt"]


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("surface", ["web", "miniapp"])
async def test_fresh_feed_repeat_sends_creator_prompt_to_real_provider(local_launch, wire, model, surface):
    result = await miniapp_routes.remix_feed_post(
        77, miniapp_routes.FeedRemixRequest(
            model=model, image_url=REFS[0], reference_urls=REFS[1:], mode="image",
            change_request="make the coat blue", quality="2K",
        ), session=local_launch.session, user=local_launch.user, surface=surface,
    )
    params = wire[0]["body"]["params"]
    assert params["model_name"] == model
    assert params["image_urls"] == REFS
    assert SECRET in params["prompt"]
    assert IDENTITY_RULE not in params["prompt"]
    assert "make the coat blue" in params["prompt"]
    assert SECRET not in str(result)
    context = repo.create_generation.await_args.kwargs["input_params"][prompt_core.FEED_REMIX_CONTEXT_KEY]
    assert context["version"] == 4
    assert "prompt" not in context


@pytest.mark.parametrize("model", MODELS)
async def test_all_public_gallery_aliases_are_excluded_from_identity_roles(local_launch, wire, monkeypatch, model):
    monkeypatch.setattr(miniapp_routes.settings, "WEB_PUBLIC_URL", "https://app.example.test")
    local_launch.source.result_urls = json.dumps([SOURCE, OTHER_SOURCE])
    await miniapp_routes.remix_feed_post(
        77, miniapp_routes.FeedRemixRequest(
            model=model, image_url=REFS[0],
            source_image_url=f"https://app.example.test/api/v1/feed/77/display.webp?index=1&output_id={feed_media.feed_source_output_id(local_launch.source, OTHER_SOURCE)}",
            reference_urls=[SOURCE, f"https://app.example.test/api/v1/feed/77/preview.webp?index=0&output_id={feed_media.feed_source_output_id(local_launch.source, SOURCE)}", REFS[1], OTHER_SOURCE],
        ), session=local_launch.session, user=local_launch.user,
    )
    params = wire[0]["body"]["params"]
    assert params["image_urls"] == REFS[:2]
    assert params["prompt"] == SECRET


@pytest.mark.parametrize("model", MODELS)
async def test_personalized_repeat_overflow_fails_before_charge(local_launch, wire, model):
    with pytest.raises(HTTPException) as error:
        await miniapp_routes.remix_feed_post(
            77, miniapp_routes.FeedRemixRequest(
                model=model, reference_urls=[*REFS, "https://example.test/fourth-person.jpg", "https://example.test/fifth-person.jpg"],
                change_request="blue coat", mode="image",
            ), session=local_launch.session, user=local_launch.user,
        )
    assert error.value.status_code == 422
    assert wire == []
    repo.charge_image_generation.assert_not_awaited()
    repo.create_generation.assert_not_awaited()


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("references", [[], [SOURCE]])
async def test_change_only_repeat_requires_reader_reference(local_launch, wire, model, references):
    with pytest.raises(HTTPException) as error:
        await miniapp_routes.remix_feed_post(
            77, miniapp_routes.FeedRemixRequest(
                model=model, reference_urls=references, change_request="make the coat blue", mode="image",
            ), session=local_launch.session, user=local_launch.user,
        )
    assert error.value.status_code == 422
    assert wire == []
    repo.charge_image_generation.assert_not_awaited()


@pytest.mark.parametrize("model", MODELS)
async def test_unavailable_supplied_identity_fails_without_scene_only_fallback(local_launch, wire, monkeypatch, model):
    monkeypatch.setattr(miniapp_routes, "public_url_is_available", lambda url: url != REFS[1])
    with pytest.raises(HTTPException) as error:
        await miniapp_routes.remix_feed_post(
            77, miniapp_routes.FeedRemixRequest(model=model, reference_urls=REFS[:2]),
            session=local_launch.session, user=local_launch.user,
        )
    assert error.value.status_code == 422
    assert wire == []
    repo.charge_image_generation.assert_not_awaited()
    repo.create_generation.assert_not_awaited()


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("metadata", [None, {"hidden_prompt": False}, '{"hidden_prompt": false}'])
async def test_own_visible_recipe_uses_reader_photo_without_finished_author_image(local_launch, wire, model, metadata):
    local_launch.source.user_id = local_launch.user.id
    local_launch.source.prompt = OWN_RECIPE
    local_launch.source.source_feed_gen_id = None
    local_launch.source.input_params = metadata
    await miniapp_routes.remix_feed_post(
        77, miniapp_routes.FeedRemixRequest(
            model=model, image_url=REFS[0], reference_urls=[SOURCE], change_request="make the coat blue",
        ), session=local_launch.session, user=local_launch.user,
    )
    params = wire[0]["body"]["params"]
    assert params["image_urls"] == REFS[:1]
    assert OWN_RECIPE in params["prompt"]
    assert "EXCLUSIVE source" not in params["prompt"]
    assert "make the coat blue" in params["prompt"]


@pytest.mark.parametrize("metadata,lineage", [
    ({"hidden_prompt": True}, None), ({"hidden_prompt": False}, 55), (None, 55),
    ("malformed-json", None), (["not-an-object"], None), ("null", None),
    ("[]", None), ("false", None), (False, None),
])
async def test_owner_hidden_or_derivative_recipe_without_public_origin_fails_closed(local_launch, wire, metadata, lineage):
    local_launch.source.user_id = local_launch.user.id
    local_launch.source.source_feed_gen_id = lineage
    local_launch.source.input_params = metadata
    with pytest.raises(HTTPException) as error:
        await miniapp_routes.remix_feed_post(
            77, miniapp_routes.FeedRemixRequest(model="nano-banana-pro", image_url=REFS[0]),
            session=local_launch.session, user=local_launch.user,
        )
    assert error.value.status_code == 422
    assert wire == []
    repo.charge_image_generation.assert_not_awaited()


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("references", [REFS[:1], REFS, [REFS[2]]])
@pytest.mark.parametrize("selected_source", [SOURCE, OTHER_SOURCE])
async def test_fresh_web_result_repeated_in_telegram_rebuilds_current_reference_roles(
    local_launch, wire, monkeypatch, model, references, selected_source,
):
    launch = local_launch
    launch.source.result_urls = json.dumps([SOURCE, OTHER_SOURCE])
    await miniapp_routes.remix_feed_post(
        77, miniapp_routes.FeedRemixRequest(
            model=model, image_url=REFS[0], change_request="blue coat", source_image_url=selected_source,
        ),
        session=launch.session, user=launch.user, surface="web",
    )
    saved = repo.create_generation.await_args
    launch.generation.prompt = saved.args[4]
    launch.generation.input_params = saved.kwargs["input_params"]
    launch.generation.source_feed_gen_id = 77
    launch.generation.model = model
    image_session = launch.created_sessions[-1]
    image_session.reference_url = references[0]
    image_session.reference_urls = json.dumps(references + [selected_source])
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(
        side_effect=lambda _session, gid: launch.source if gid == 77 else launch.generation,
    ))
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(image_session, 99)))
    state, _ = mutable_state({
        "pending_image_prompt": launch.generation.prompt,
        "pending_parent_generation_id": 99, "pending_source_feed_gen_id": 77,
        "image_session_id": image_session.id,
    })
    await image_gen.cb_image_repeat_launch(
        SimpleNamespace(message=AsyncMock(), answer=AsyncMock()),
        launch.session, state, launch.user, AsyncMock(),
    )
    assert len(wire) == 2
    params = wire[-1]["body"]["params"]
    assert params["model_name"] == model
    assert params["image_urls"] == references
    assert SECRET in params["prompt"]
    assert IDENTITY_RULE not in params["prompt"]
    assert "blue coat" in params["prompt"]
    assert wire[0]["key"] != wire[1]["key"]
    assert "seed" not in params


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("version", [1, 2])
async def test_trusted_legacy_next_repeat_upgrades_actual_provider_payload(local_launch, wire, monkeypatch, model, version):
    header = prompt_core._LEGACY_SOURCE_FIRST_PROMPT if version == 1 else prompt_core._USER_FIRST_SOURCE_LAST_PROMPT
    previous = previous_generation(header + "\n\nmake the coat blue", version=version)
    image_session = await repo.create_image_session(
        local_launch.session, local_launch.user.id, model, "image", "1:1", "2K", 1,
        None, reference_urls=REFS[:2] + [SOURCE],
    )
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(
        side_effect=lambda _session, gid: local_launch.source if gid == 77 else previous,
    ))
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(image_session, 88)))
    state, _ = mutable_state({
        "pending_image_prompt": previous.prompt, "pending_parent_generation_id": 88,
        "pending_source_feed_gen_id": 77, "image_session_id": image_session.id,
    })
    await image_gen.cb_image_repeat_launch(
        SimpleNamespace(message=AsyncMock(), answer=AsyncMock()),
        local_launch.session, state, local_launch.user, AsyncMock(),
    )
    assert len(wire) == 1
    params = wire[0]["body"]["params"]
    assert params["image_urls"] == REFS[:2]
    assert SECRET in params["prompt"]
    assert IDENTITY_RULE not in params["prompt"]
    assert "make the coat blue" in params["prompt"]
    assert repo.create_generation.await_args.kwargs["input_params"][prompt_core.FEED_REMIX_CONTEXT_KEY]["version"] == 4


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("intent", ["current", "stale_session", "stale_parent", "foreign_session", "string_flag", "action_only", "repeat"])
async def test_personalized_telegram_edit_uses_creator_recipe_with_stale_state(local_launch, wire, monkeypatch, model, intent):
    image_session = await repo.create_image_session(
        local_launch.session, local_launch.user.id, model, "image", "1:1", "2K", 1,
        None, reference_urls=[REFS[0], SOURCE],
    )
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(return_value=local_launch.source))
    data = {"remix_mode": True, "image_session_id": image_session.id, "remix_parent_generation_id": 77}
    if intent == "stale_session":
        data["image_session_id"] += 100
    elif intent == "stale_parent":
        data["remix_parent_generation_id"] = 123
    elif intent == "foreign_session":
        image_session.user_id = 9
    elif intent == "string_flag":
        data["remix_mode"] = "true"
    elif intent == "action_only":
        data = {}
    state, _ = mutable_state(data)
    assert await image_gen._launch_session_generation(
        source_message=AsyncMock(), state=state, session=local_launch.session, db_user=local_launch.user,
        image_session=image_session, prompt=SECRET,
        action_type=ImageGenerationAction.repeat if intent == "repeat" else ImageGenerationAction.remix,
        reference_url=[REFS[0], SOURCE], parent_generation_id=77, source_feed_gen_id=77,
        feed_change_request="change my hair color", launching_text="launch", queued_text="queued",
    )
    prompt = wire[0]["body"]["params"]["prompt"]
    assert wire[0]["body"]["params"]["image_urls"] == [REFS[0]]
    assert SECRET in prompt
    assert IDENTITY_RULE not in prompt
    assert "change my hair color" in prompt


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("suffix", ["", SUFFIX])
def test_known_legacy_header_migration_preserves_suffix_bytes(version, suffix):
    header = prompt_core._LEGACY_SOURCE_FIRST_PROMPT if version == 1 else prompt_core._USER_FIRST_SOURCE_LAST_PROMPT
    migrated = prompt_core.trusted_feed_image_prompt(
        previous_generation(header + suffix, version=version), user_id=42,
        source_generation_id=77, has_user_references=True,
    )
    assert_face_replacement(migrated)
    assert migrated.partition("\n\n")[2] == suffix.removeprefix("\n\n")
    assert migrated.endswith(suffix)


@pytest.mark.parametrize("suffix", ["\nuser suffix", "garbage", " \n\nuser suffix"])
def test_partial_generic_header_is_not_rewritten(suffix):
    original = prompt_core._USER_FIRST_SOURCE_LAST_PROMPT + suffix
    assert prompt_core.trusted_feed_image_prompt(
        previous_generation(original), user_id=42, source_generation_id=77, has_user_references=True,
    ) == original


def test_unknown_authenticated_text_is_preserved_verbatim():
    original = "Verified user-authored variation text" + SUFFIX
    assert prompt_core.trusted_feed_image_prompt(
        previous_generation(original), user_id=42, source_generation_id=77, has_user_references=True,
    ) == original


@pytest.mark.parametrize("tamper", ["owner", "lineage", "source", "prompt", "metadata", "context", True, False, 1.0, "2", 99])
def test_context_tampering_fails_closed_before_prompt_migration(tamper):
    saved = previous_generation(prompt_core._USER_FIRST_SOURCE_LAST_PROMPT + SUFFIX)
    context = saved.input_params[prompt_core.FEED_REMIX_CONTEXT_KEY]
    if tamper == "owner":
        saved.user_id = 9
    elif tamper == "lineage":
        saved.source_feed_gen_id = 55
    elif tamper == "source":
        context["source_generation_id"] = 55
    elif tamper == "prompt":
        saved.prompt += "tampered"
    elif tamper == "metadata":
        saved.input_params = "not-json"
    elif tamper == "context":
        saved.input_params[prompt_core.FEED_REMIX_CONTEXT_KEY] = []
    else:
        context["version"] = tamper
    assert prompt_core.trusted_feed_image_prompt(
        saved, user_id=42, source_generation_id=77, has_user_references=True,
    ) is None


def test_v3_current_relative_roles_survive_removal_and_readdition():
    original = prompt_core.build_feed_image_prompt(has_user_references=True, has_source_media=True) + SUFFIX
    saved = previous_generation(original)
    saved.input_params[prompt_core.FEED_REMIX_CONTEXT_KEY] = prompt_core.feed_image_remix_context(77, original)
    without_identity = prompt_core.trusted_feed_image_prompt(
        saved, user_id=42, source_generation_id=77, has_user_references=False,
    )
    assert "EXCLUSIVE source" not in without_identity
    assert "new pose, framing and composition" in without_identity
    assert without_identity.endswith(SUFFIX)
    saved.prompt = without_identity
    saved.input_params[prompt_core.FEED_REMIX_CONTEXT_KEY] = prompt_core.feed_image_remix_context(77, without_identity)
    restored = prompt_core.trusted_feed_image_prompt(
        saved, user_id=42, source_generation_id=77, has_user_references=True,
    )
    assert_face_replacement(restored)
    assert "All images preceding the final image" in restored
    assert restored.endswith(SUFFIX)


def test_old_v3_variation_metadata_still_replays_as_identity_replacement():
    # Already paid v3 generations must remain authenticated after changing
    # the default semantic role contract. Preserve user change suffix verbatim.
    legacy = prompt_core._IMAGE_VARIATION_PROMPT + SUFFIX
    previous = previous_generation(legacy, version=3)
    previous.input_params[prompt_core.FEED_REMIX_CONTEXT_KEY] = {
        "version": 3,
        "source_generation_id": 77,
        "prompt": legacy,
        "header_family": "variation",
        "source_image_url": SOURCE,
        "scene_generation_id": 77,
    }
    restored = prompt_core.trusted_feed_image_prompt(
        previous, user_id=42, source_generation_id=77,
        has_user_references=True,
    )
    assert_face_replacement(restored)
    assert restored.endswith(SUFFIX)
    assert prompt_core.trusted_feed_image_scene(
        previous, user_id=42, source_generation_id=77,
    ) == (77, SOURCE)


def test_previous_v3_face_replacement_replay_migrates_to_source_first_and_preserves_user_edit():
    old = prompt_core._IMAGE_FACE_REPLACEMENT_PROMPT + SUFFIX
    previous = previous_generation(old, version=3)
    previous.input_params[prompt_core.FEED_REMIX_CONTEXT_KEY] = {
        "version": 3, "source_generation_id": 77,
        "prompt": old, "header_family": "face_replacement",
        "scene_generation_id": 77, "source_image_url": SOURCE,
    }
    restored = prompt_core.trusted_feed_image_prompt(
        previous, user_id=42, source_generation_id=77,
        has_user_references=True, scene_first=True,
    )
    assert restored == prompt_core._LEGACY_SOURCE_FIRST_PROMPT + SUFFIX
    assert prompt_core.trusted_feed_image_scene(
        previous, user_id=42, source_generation_id=77,
    ) == (77, SOURCE)



@pytest.mark.parametrize("version", [1, 2])
def test_image_semantics_do_not_change_legacy_video_migration(version):
    header = prompt_core._LEGACY_SOURCE_FIRST_PROMPT if version == 1 else prompt_core._USER_FIRST_SOURCE_LAST_PROMPT
    saved = previous_generation(header + SUFFIX, version=version)
    video_prompt = prompt_core.trusted_feed_prompt(saved, user_id=42, source_generation_id=77)
    assert video_prompt == prompt_core._USER_FIRST_SOURCE_LAST_PROMPT + SUFFIX
    assert "Preserve its visible composition" in video_prompt
    assert "new pose" not in video_prompt


@pytest.mark.parametrize("family", [[], {}, True, "unknown", "scene_edit"])
def test_v3_malformed_or_mismatched_header_family_fails_closed(family):
    prompt = prompt_core.build_feed_image_prompt(has_user_references=True, has_source_media=True)
    saved = previous_generation(prompt)
    context = prompt_core.feed_image_remix_context(77, prompt)
    context["header_family"] = family
    saved.input_params[prompt_core.FEED_REMIX_CONTEXT_KEY] = context
    assert prompt_core.trusted_feed_image_prompt(
        saved, user_id=42, source_generation_id=77, has_user_references=True,
    ) is None


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("edit_prompt", [False, True])
async def test_safe_repeat_same_confirm_submits_once_but_new_repeat_is_fresh(
    local_launch, wire, monkeypatch, model, edit_prompt,
):
    """The repository fake models durable confirm lookup, not provider dedupe."""
    launch = local_launch
    original = launch.generation
    original.model = model
    original.image_session_id = None
    original.source_feed_gen_id = 77
    original.prompt = prompt_core._USER_FIRST_SOURCE_LAST_PROMPT + "\n\nblue coat"
    original.input_params = {
        "reference_images": REFS[:2] + [SOURCE],
        prompt_core.FEED_REMIX_CONTEXT_KEY: {
            "version": 2, "source_generation_id": 77, "prompt": original.prompt,
        },
    }
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(
        side_effect=lambda _session, gid: launch.source if gid == 77 else original,
    ))
    monkeypatch.setattr(repeat_safe, "get_repeat_task_by_any_id", AsyncMock(return_value=original))
    monkeypatch.setattr(repeat_safe, "_is_admin", lambda _user: False)
    monkeypatch.setattr(repeat_safe, "safe_answer_callback", AsyncMock())
    persisted = {}

    async def create_generation(*_args, **_kwargs):
        context = current_repeat_launch_context()
        assert context is not None
        confirm_key = context.input_params_extra["repeat_confirm_key"]
        assert confirm_key not in persisted
        generated = SimpleNamespace(id=100 + len(persisted), task_id="queued", status="processing")
        persisted[confirm_key] = generated
        return generated

    monkeypatch.setattr(repo, "create_generation", AsyncMock(side_effect=create_generation))
    monkeypatch.setattr(repeat_safe, "find_repeat_by_confirm_key", AsyncMock(
        side_effect=lambda _session, *, user_id, confirm_key: persisted.get(confirm_key),
    ))
    call = SimpleNamespace(
        data="repeat_image_img_99", from_user=SimpleNamespace(id=777),
        message=AsyncMock(), answer=AsyncMock(),
    )
    state, data = mutable_state()
    await repeat_safe.open_repeat(call, launch.session, state, launch.user, AsyncMock())
    first_key = data["repeat_confirm_key"]
    if edit_prompt:
        await repeat_safe.save_repeat_prompt(
            SimpleNamespace(text="change my hair color", answer=AsyncMock()), state,
        )
    delayed_duplicate, _ = mutable_state(data)
    await repeat_safe.confirm_repeat(call, launch.session, state, launch.user, AsyncMock())
    await repeat_safe.confirm_repeat(call, launch.session, delayed_duplicate, launch.user, AsyncMock())
    assert len(wire) == 1
    assert repo.charge_image_generation.await_count == 1
    assert SECRET in wire[0]["body"]["params"]["prompt"]
    assert "blue coat" in wire[0]["body"]["params"]["prompt"]
    if edit_prompt:
        assert "change my hair color" in wire[0]["body"]["params"]["prompt"]
    await repeat_safe.open_repeat(call, launch.session, state, launch.user, AsyncMock())
    assert data["repeat_confirm_key"] != first_key
    await repeat_safe.confirm_repeat(call, launch.session, state, launch.user, AsyncMock())
    assert len(wire) == 2
    assert repo.charge_image_generation.await_count == 2
    assert len(persisted) == 2
    assert wire[0]["key"] != wire[1]["key"]
    for submitted in wire:
        params = submitted["body"]["params"]
        assert params["image_urls"] == REFS[:2]
        assert "seed" not in params
        assert SECRET in params["prompt"]
        assert IDENTITY_RULE not in params["prompt"]


@pytest.mark.parametrize("model", MODELS)
async def test_missing_saved_identity_blocks_safe_repeat_before_creating_or_charging(local_launch, wire, monkeypatch, model):
    launch = local_launch
    original = launch.generation
    original.model = model
    original.image_session_id = None
    original.source_feed_gen_id = 77
    original.input_params = {"reference_images": [REFS[0], SOURCE]}
    monkeypatch.setattr(repeat_safe, "get_repeat_task_by_any_id", AsyncMock(return_value=original))
    monkeypatch.setattr(repeat_safe, "find_repeat_by_confirm_key", AsyncMock(return_value=None))
    monkeypatch.setattr(repeat_safe, "_is_admin", lambda _user: False)
    monkeypatch.setattr(repeat_safe, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(repeat_safe, "public_url_is_available", lambda url: url != REFS[0])
    call = SimpleNamespace(
        data="repeat_image_img_99", from_user=SimpleNamespace(id=777),
        message=AsyncMock(), answer=AsyncMock(),
    )
    state, data = mutable_state()
    await repeat_safe.open_repeat(call, launch.session, state, launch.user, AsyncMock())
    assert data["repeat_missing_references"] == [REFS[0]]
    await repeat_safe.confirm_repeat(call, launch.session, state, launch.user, AsyncMock())
    assert wire == []
    repo.charge_image_generation.assert_not_awaited()
    repo.create_generation.assert_not_awaited()


@pytest.mark.parametrize("model", MODELS)
async def test_own_visible_recipe_and_previous_changes_survive_safe_repeat(local_launch, wire, monkeypatch, model):
    launch = local_launch
    launch.source.user_id = launch.user.id
    launch.source.prompt = OWN_RECIPE
    launch.source.input_params = None
    launch.source.source_feed_gen_id = None
    await miniapp_routes.remix_feed_post(
        77, miniapp_routes.FeedRemixRequest(
            model=model, image_url=REFS[0], change_request="blue coat with silver buttons",
        ), session=launch.session, user=launch.user,
    )
    saved = repo.create_generation.await_args
    original_prompt = wire[0]["body"]["params"]["prompt"]
    original = launch.generation
    original.model = model
    original.prompt = saved.args[4]
    original.source_feed_gen_id = saved.kwargs["source_feed_gen_id"]
    original.input_params = {**(saved.kwargs["input_params"] or {}), "reference_images": REFS[:1]}
    original.image_session_id = None
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(
        side_effect=lambda _session, gid: launch.source if gid == 77 else original,
    ))
    monkeypatch.setattr(repeat_safe, "get_repeat_task_by_any_id", AsyncMock(return_value=original))
    monkeypatch.setattr(repeat_safe, "find_repeat_by_confirm_key", AsyncMock(return_value=None))
    monkeypatch.setattr(repeat_safe, "_is_admin", lambda _user: False)
    monkeypatch.setattr(repeat_safe, "safe_answer_callback", AsyncMock())
    call = SimpleNamespace(
        data="repeat_image_img_99", from_user=SimpleNamespace(id=777),
        message=AsyncMock(), answer=AsyncMock(),
    )
    state, _ = mutable_state()
    await repeat_safe.open_repeat(call, launch.session, state, launch.user, AsyncMock())
    await repeat_safe.confirm_repeat(call, launch.session, state, launch.user, AsyncMock())
    assert len(wire) == 2
    assert wire[1]["body"]["params"]["prompt"] == original_prompt
    assert wire[1]["body"]["params"]["image_urls"] == REFS[:1]
    assert "blue coat with silver buttons" in original_prompt
    assert OWN_RECIPE in original_prompt


@pytest.mark.parametrize("model", MODELS)
async def test_expired_gallery_entry_does_not_promote_bound_display_alias_to_identity(local_launch, wire, monkeypatch, model):
    monkeypatch.setattr(miniapp_routes.settings, "WEB_PUBLIC_URL", "https://app.example.test")
    monkeypatch.setattr(miniapp_routes, "public_url_is_available", lambda url: url != SOURCE)
    monkeypatch.setattr(feed_media, "public_url_is_available", lambda url: url != SOURCE)
    local_launch.source.result_urls = json.dumps([SOURCE, OTHER_SOURCE])
    await miniapp_routes.remix_feed_post(
        77, miniapp_routes.FeedRemixRequest(
            model=model, image_url=REFS[0], source_image_url=OTHER_SOURCE,
            reference_urls=[SOURCE, f"https://app.example.test/api/v1/feed/77/display.webp?index=1&output_id={feed_media.feed_source_output_id(local_launch.source, OTHER_SOURCE)}"],
        ), session=local_launch.session, user=local_launch.user,
    )
    params = wire[0]["body"]["params"]
    assert params["image_urls"] == [REFS[0]]
    assert params["prompt"] == SECRET


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("entrypoint", ["remix", "style"])
async def test_actual_explicit_telegram_callback_binds_edit_of_current_result(local_launch, wire, monkeypatch, model, entrypoint):
    launch = local_launch
    image_session = await repo.create_image_session(
        launch.session, launch.user.id, model, "image", "1:1", "2K", 1,
        None, reference_urls=REFS[:1] + [SOURCE],
    )
    image_session.last_generation_id = 99
    image_session.last_result_url = OTHER_SOURCE
    launch.generation.source_feed_gen_id = 77
    launch.generation.result_url = OTHER_SOURCE
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(
        side_effect=lambda _session, gid: launch.source if gid == 77 else launch.generation,
    ))
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(image_session, 99)))
    monkeypatch.setattr(image_gen, "safe_edit_message", AsyncMock())
    state, data = mutable_state()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), data="img_session:remix:99")
    if entrypoint == "remix":
        await image_gen.cb_image_session_remix(call, launch.session, state, launch.user)
    else:
        call.data = "img_style:hair_color:99"
        await image_gen.cb_image_style_choice(call, launch.session, state, launch.user)
    assert data["remix_mode"] is True
    assert data["remix_parent_generation_id"] == 99
    assert data["image_session_id"] == image_session.id
    assert await image_gen._launch_session_generation(
        source_message=call.message, state=state, session=launch.session, db_user=launch.user,
        image_session=image_session, prompt=SECRET, action_type=ImageGenerationAction.remix,
        reference_url=[REFS[0], data["remix_reference_url"]], parent_generation_id=99,
        source_feed_gen_id=77, feed_change_request="make the coat blue", launching_text="launch", queued_text="queued",
    )
    params = wire[0]["body"]["params"]
    assert params["image_urls"] == [OTHER_SOURCE, REFS[0]]
    assert_scene_first_edit(params["prompt"])
    assert "Preserve its visible composition" in params["prompt"]


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("owns_source", [False, True])
async def test_quote_and_submit_share_authenticated_own_recipe_reference_budget(local_launch, wire, model, owns_source):
    launch = local_launch
    launch.source.user_id = launch.user.id if owns_source else 100
    launch.source.prompt = OWN_RECIPE if owns_source else SECRET
    launch.source.input_params = {"hidden_prompt": False}
    references = REFS + ["https://example.test/fourth-identity.jpg"]
    # Client hints never grant ownership; the server decides which recipe is public.
    body = miniapp_routes.FeedRemixRequest.model_validate({
        "model": model, "reference_urls": references,
        "is_owner": True, "can_view_prompt": True, "user_id": 100, "prompt_hidden": False,
    })
    quote = await miniapp_routes.quote_feed_remix(77, body, session=launch.session, user=launch.user)
    assert quote["can_run"] is True
    assert quote["cost_credits"] == 4
    assert wire == []
    repo.charge_image_generation.assert_not_awaited()
    await miniapp_routes.remix_feed_post(77, body, session=launch.session, user=launch.user)
    assert wire[0]["body"]["params"]["image_urls"] == references
    assert (OWN_RECIPE if owns_source else SECRET) in wire[0]["body"]["params"]["prompt"]
    if not owns_source:
        assert wire[0]["body"]["params"]["prompt"] == SECRET
        context = repo.create_generation.await_args.kwargs["input_params"][prompt_core.FEED_REMIX_CONTEXT_KEY]
        assert context["version"] == 4 and "prompt" not in context


@pytest.mark.parametrize("model", MODELS)
async def test_repeat_after_explicit_edit_keeps_owned_derived_scene_separate_from_identity(local_launch, wire, monkeypatch, model):
    launch = local_launch
    image_session = await repo.create_image_session(
        launch.session, launch.user.id, model, "image", "1:1", "2K", 1,
        None, reference_urls=[REFS[0], OTHER_SOURCE],
    )
    derived = launch.generation
    derived.source_feed_gen_id = 77
    derived.result_url = OTHER_SOURCE
    records = {77: launch.source, 99: derived}
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(side_effect=lambda _session, gid: records.get(gid)))
    state, _ = mutable_state({
        "remix_mode": True, "image_session_id": image_session.id, "remix_parent_generation_id": 99,
    })
    assert await image_gen._launch_session_generation(
        source_message=AsyncMock(), state=state, session=launch.session, db_user=launch.user,
        image_session=image_session, prompt=SECRET, action_type=ImageGenerationAction.remix,
        reference_url=[REFS[0], OTHER_SOURCE], parent_generation_id=99,
        source_feed_gen_id=77, feed_change_request="make the coat blue", launching_text="launch", queued_text="queued",
    )
    saved = repo.create_generation.await_args
    records[101] = SimpleNamespace(
        id=101, user_id=42, source_feed_gen_id=77, prompt=saved.args[4],
        input_params=saved.kwargs["input_params"],
    )
    assert await image_gen._launch_session_generation(
        source_message=AsyncMock(), state=mutable_state()[0], session=launch.session, db_user=launch.user,
        image_session=image_session, prompt=records[101].prompt, action_type=ImageGenerationAction.repeat,
        reference_url=[REFS[0], OTHER_SOURCE], parent_generation_id=101,
        source_feed_gen_id=77, launching_text="launch", queued_text="queued",
    )
    assert len(wire) == 2
    assert wire[-1]["body"]["params"]["image_urls"] == [OTHER_SOURCE, REFS[0]]
    assert_scene_first_edit(wire[-1]["body"]["params"]["prompt"])
    assert wire[-1]["body"]["params"]["prompt"].endswith("make the coat blue")


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("failure", ["tampered_digest", "wrong_source", "expired_reader_photo"])
async def test_invalid_saved_recipe_or_reader_photo_fails_before_another_charge(local_launch, wire, monkeypatch, model, failure):
    launch = local_launch
    launch.source.result_urls = json.dumps([SOURCE, OTHER_SOURCE])
    await miniapp_routes.remix_feed_post(
        77, miniapp_routes.FeedRemixRequest(
            model=model, image_url=REFS[0], source_image_url=OTHER_SOURCE, change_request="blue coat",
        ), session=launch.session, user=launch.user,
    )
    saved = repo.create_generation.await_args
    original = launch.generation
    original.source_feed_gen_id = 77
    original.prompt = saved.args[4]
    original.input_params = saved.kwargs["input_params"]
    context = original.input_params[prompt_core.FEED_REMIX_CONTEXT_KEY]
    if failure == "tampered_digest":
        context["prompt_sha256"] = "0" * 64
    elif failure == "wrong_source":
        context["source_generation_id"] = 55
    else:
        monkeypatch.setattr(image_gen, "public_url_is_available", lambda url: url != REFS[0])
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(
        side_effect=lambda _session, gid: {77: launch.source, 99: original}.get(gid),
    ))
    image_session = launch.created_sessions[-1]
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(image_session, 99)))
    state, _ = mutable_state({
        "pending_image_prompt": original.prompt, "pending_parent_generation_id": 99,
        "pending_source_feed_gen_id": 77, "image_session_id": image_session.id,
    })
    repo.charge_image_generation.reset_mock()
    repo.create_generation.reset_mock()
    await image_gen.cb_image_repeat_launch(
        SimpleNamespace(message=AsyncMock(), answer=AsyncMock()),
        launch.session, state, launch.user, AsyncMock(),
    )
    assert len(wire) == 1
    repo.charge_image_generation.assert_not_awaited()
    repo.create_generation.assert_not_awaited()


@pytest.mark.parametrize("model", MODELS)
async def test_feed_again_expired_saved_identity_keeps_existing_session_before_charge(local_launch, wire, monkeypatch, model):
    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, model, "image", "1:1", "2K", 1,
        None, reference_urls=[REFS[0], SOURCE],
    )
    original = launch.generation
    original.model = model
    original.image_session_id = old.id
    original.source_feed_gen_id = 77
    original.prompt = prompt_core._USER_FIRST_SOURCE_LAST_PROMPT
    original.input_params = {
        prompt_core.FEED_REMIX_CONTEXT_KEY: {
            "version": 2, "source_generation_id": 77, "prompt": original.prompt,
        },
    }
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(
        side_effect=lambda _session, gid: launch.source if gid == 77 else original,
    ))
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(image_gen, "public_url_is_available", lambda url: url != REFS[0])
    repo.archive_active_image_sessions.reset_mock()
    state, data = mutable_state({"existing_session": old.id})
    await feed.cb_feed_again(
        SimpleNamespace(data="feed:again:99", message=AsyncMock(), answer=AsyncMock()),
        launch.session, launch.user, state, AsyncMock(),
    )
    assert wire == []
    assert launch.created_sessions == [old]
    assert data == {"existing_session": old.id}
    repo.archive_active_image_sessions.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    repo.create_generation.assert_not_awaited()


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("expired", [False, True])
async def test_legacy_alias_selection_cannot_shift_after_gallery_expiry(local_launch, wire, monkeypatch, model, version, expired):
    from bot.utils import feed_media

    launch = local_launch
    monkeypatch.setattr(feed_media.settings, "WEB_PUBLIC_URL", "https://app.example.test")
    def available(url):
        return not (expired and url == SOURCE)

    monkeypatch.setattr(feed_media, "public_url_is_available", available)
    monkeypatch.setattr(image_gen, "public_url_is_available", available)
    launch.source.result_urls = json.dumps([SOURCE, OTHER_SOURCE])
    header = prompt_core._LEGACY_SOURCE_FIRST_PROMPT if version == 1 else prompt_core._USER_FIRST_SOURCE_LAST_PROMPT
    previous = previous_generation(header + "\n\nblue coat", version=version)
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(
        side_effect=lambda _session, gid: {77: launch.source, 88: previous}.get(gid),
    ))
    alias = "https://app.example.test/api/v1/feed/77/preview.webp?index=0"
    image_session = await repo.create_image_session(
        launch.session, launch.user.id, model, "image", "1:1", "2K", 1,
        None, reference_urls=[REFS[0], alias],
    )
    launched = await image_gen._launch_session_generation(
        source_message=AsyncMock(), state=mutable_state()[0], session=launch.session, db_user=launch.user,
        image_session=image_session, prompt=previous.prompt, action_type=ImageGenerationAction.repeat,
        reference_url=[REFS[0], alias], parent_generation_id=88, source_feed_gen_id=77,
        launching_text="launch", queued_text="queued",
    )
    assert launched is True
    assert wire[0]["body"]["params"]["image_urls"] == [REFS[0]]
    assert SECRET in wire[0]["body"]["params"]["prompt"]
    assert "blue coat" in wire[0]["body"]["params"]["prompt"]


@pytest.mark.parametrize("model", [*MODELS, "midjourney-imagine", "midjourney-blend"])
@pytest.mark.parametrize("permission", ["own", "foreign", "hidden", "derived", "malformed"])
@pytest.mark.parametrize("personalized", [False, True])
async def test_http_own_recipe_result_keeps_share_and_session_provenance_without_prompt_leak(local_launch, wire, monkeypatch, model, permission, personalized):
    from fastapi import FastAPI

    from api.miniapp_auth import get_miniapp_user
    from db.models import GenerationStatus
    from db.session import get_session

    launch = local_launch
    launch.source.user_id = 100 if permission == "foreign" else launch.user.id
    launch.source.prompt = OWN_RECIPE if permission == "own" else SECRET
    launch.source.source_feed_gen_id = 55 if permission == "derived" else None
    launch.source.input_params = {"hidden_prompt": True} if permission == "hidden" else "bad-json" if permission == "malformed" else None
    generated = launch.generation
    submitted = AsyncMock(return_value="synthetic-midjourney-task")
    if model == "midjourney-blend":
        launch.source.result_urls = json.dumps([SOURCE, OTHER_SOURCE])
        monkeypatch.setattr(miniapp_routes.midjourney_service, "blend", submitted)
        monkeypatch.setattr(miniapp_routes, "_data_uri_from_url", AsyncMock(side_effect=lambda url: "data:" + url))
    elif model == "midjourney-imagine":
        monkeypatch.setattr(miniapp_routes.midjourney_service, "imagine", submitted)

    async def persist(*args, **kwargs):
        generated.prompt = args[4]
        generated.model = model
        generated.source_feed_gen_id = kwargs.get("source_feed_gen_id")
        generated.input_params = kwargs.get("input_params")
        return generated

    monkeypatch.setattr(repo, "create_generation", AsyncMock(side_effect=persist))
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(return_value=generated))
    monkeypatch.setattr(miniapp_routes, "_reconcile_generation_status", AsyncMock(return_value=generated))
    share = AsyncMock(return_value=generated)
    monkeypatch.setattr(repo, "share_to_feed", share)
    generated.likes_count = generated.shares_count = 0
    monkeypatch.setattr(repo, "get_feed_generation_card", AsyncMock(return_value=SimpleNamespace(
        generation=generated, aspect_ratio="1:1", username="owner", full_name=None, remix_count=0,
    )))
    app = FastAPI()
    app.include_router(miniapp_routes.router)
    app.dependency_overrides[get_session] = lambda: launch.session
    app.dependency_overrides[get_miniapp_user] = lambda: launch.user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        edits = {}
        if personalized:
            if model == "midjourney-blend":
                edits = {"reference_urls": REFS[:2]}
            else:
                edits = {"image_url": REFS[0], "change_request": "make the coat blue"}
        response = await client.post("/api/v1/feed/77/remix", json={"model": model, **edits})
        should_run = (
            permission == "own"
            or (permission == "foreign" and personalized and model != "midjourney-blend")
        )
        if not should_run:
            assert response.status_code == 422, response.text
            repo.charge_image_generation.assert_not_awaited()
            assert launch.created_sessions == []
            return
        assert response.status_code == 202, response.text
        owned = permission == "own"
        # Established HTTP transport policy hides ALL stored prompts, even the owner's.
        assert response.json()["prompt_hidden"] is True
        assert response.json()["prompt_actions_allowed"] is False
        assert response.json()["prompt"] == ""
        assert generated.source_feed_gen_id == (None if owned else 77)
        current = launch.created_sessions[-1]
        assert current.prompt_provenance == ("user_supplied" if owned else None)
        if owned:
            assert OWN_RECIPE in generated.prompt
            assert current.base_prompt == generated.prompt
            if edits.get("change_request"):
                assert "make the coat blue" in generated.prompt
            if personalized:
                expected_refs = REFS[:2] if model == "midjourney-blend" else REFS[:1]
                assert json.loads(current.reference_urls) == expected_refs
            assert prompt_core.FEED_REMIX_CONTEXT_KEY not in (generated.input_params or {})
        else:
            assert response.json()["prompt"] == ""
            assert current.base_prompt is None
            assert SECRET in generated.prompt
            assert json.loads(current.reference_urls) == REFS[:1]
            context = generated.input_params[prompt_core.FEED_REMIX_CONTEXT_KEY]
            assert context["version"] == 4 and "prompt" not in context
            if model.startswith("midjourney-"):
                assert submitted.await_args.kwargs["reference_url"] == REFS[0]
            else:
                assert wire[0]["body"]["params"]["image_urls"] == REFS[:1]
        generated.status = GenerationStatus.done
        generated.result_url = "https://example.test/new-result.jpg"
        shared = await client.post("/api/v1/generations/99/share")
        assert shared.status_code == (200 if owned else 403), shared.text
        if not owned:
            share.assert_not_awaited()
        app.dependency_overrides[get_miniapp_user] = lambda: SimpleNamespace(id=999, tg_id=999)
        public = await client.get("/api/v1/feed/99")
        assert public.status_code == 200, public.text
        assert public.json().get("prompt") in (None, "")
        assert public.json().get("prompt_visibility") == "hidden"
        assert OWN_RECIPE not in public.text and SECRET not in public.text
        private = await client.get("/api/v1/generations/99")
        assert private.status_code == 404


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("available", [False, True])
async def test_marketplace_source_admission_preserves_real_session_and_provider_atomicity(local_launch, wire, monkeypatch, model, available):
    from bot.handlers import repeat_reference_marketplace as marketplace_refs

    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, model, "image", "1:1", "2K", 1,
        "existing accepted prompt", reference_urls=REFS[:1],
    )
    repo.archive_active_image_sessions.reset_mock()
    sessions_before = list(launch.created_sessions)
    data = {
        "feed_use_prompt": SECRET, "feed_use_gen_id": 77, "use_model_key": model,
        "feed_use_user_id": launch.user.id, "feed_original_recipe_replay": True,
        "prompt_multi_ref_file_ids": ["identity-file"], "image_session_id": old.id,
    }
    state, live = mutable_state(data)
    monkeypatch.setattr(marketplace_refs, "public_url_is_available", lambda url: available if url == REFS[0] else True)
    monkeypatch.setattr(image_gen, "public_url_is_available", lambda url: available if url == REFS[0] else True)
    monkeypatch.setattr(marketplace_refs, "mirror_telegram_file", AsyncMock(return_value=REFS[0]))
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock())
    await marketplace_refs._run(call, launch.session, launch.user, state, AsyncMock())
    if available:
        assert len(launch.created_sessions) == len(sessions_before) + 1
        repo.archive_active_image_sessions.assert_awaited_once()
        assert len(wire) == 1
        assert wire[0]["body"]["params"]["image_urls"] == [REFS[0]]
        assert SECRET in wire[0]["body"]["params"]["prompt"]
    else:
        assert launch.created_sessions == sessions_before
        repo.archive_active_image_sessions.assert_not_awaited()
        repo.charge_image_generation.assert_not_awaited()
        repo.create_generation.assert_not_awaited()
        assert live == data
        assert wire == []


@pytest.mark.parametrize("model,count,owns_source", [
    ("midjourney-imagine", 2, True),
    ("midjourney-imagine", 2, False),
    ("midjourney-blend", 1, True),
    ("midjourney-blend", 6, True),
    ("midjourney-blend", 5, False),
])
async def test_midjourney_own_recipe_preserves_reference_caps_before_charge(local_launch, monkeypatch, model, count, owns_source):
    launch = local_launch
    launch.source.user_id = launch.user.id if owns_source else 100
    body = miniapp_routes.FeedRemixRequest(
        model=model, reference_urls=[f"https://example.test/user-{i}.jpg" for i in range(count)],
    )
    imagine = AsyncMock(side_effect=AssertionError("Rejected input must never submit"))
    blend = AsyncMock(side_effect=AssertionError("Rejected input must never submit"))
    monkeypatch.setattr(miniapp_routes.midjourney_service, "imagine", imagine)
    monkeypatch.setattr(miniapp_routes.midjourney_service, "blend", blend)
    for handler in [miniapp_routes.quote_feed_remix, miniapp_routes.remix_feed_post]:
        with pytest.raises(HTTPException) as error:
            await handler(77, body, session=launch.session, user=launch.user)
        assert error.value.status_code == 422
    repo.charge_image_generation.assert_not_awaited()
    repo.create_generation.assert_not_awaited()
    assert launch.created_sessions == []
    imagine.assert_not_awaited()
    blend.assert_not_awaited()


@pytest.fixture
async def derived_repeat(local_launch, wire, monkeypatch, model):
    """Create real server scene provenance through the explicit feed-remix callback."""
    from db.models import GenerationStatus

    launch = local_launch
    derived = SimpleNamespace(**{
        **vars(launch.generation), "id": 88, "model": model, "source_feed_gen_id": 77,
        "result_url": OTHER_SOURCE, "status": GenerationStatus.done,
    })
    records = {77: launch.source, 88: derived}
    generated = []

    async def persist(*args, **kwargs):
        result = SimpleNamespace(**{
            **vars(launch.generation), "id": 100 + len(generated), "model": model,
            "prompt": args[4], "source_feed_gen_id": kwargs["source_feed_gen_id"],
            "input_params": kwargs["input_params"], "image_session_id": kwargs["image_session_id"],
        })
        generated.append(result)
        records[result.id] = result
        return result

    monkeypatch.setattr(repo, "create_generation", AsyncMock(side_effect=persist))
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(side_effect=lambda _session, gid: records.get(gid)))
    monkeypatch.setattr(repo, "get_public_feed_generation", AsyncMock(side_effect=lambda _session, gid: launch.source if gid == 77 else None))
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(side_effect=lambda _session, sid, uid: next(
        (item for item in launch.created_sessions if item.id == sid and item.user_id == uid), None,
    )))
    state, data = mutable_state()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), data="feed:remix:88")
    await feed.cb_feed_remix(call, launch.session, launch.user, state)
    current = launch.created_sessions[-1]
    # User photos accepted into the current edit session before its first submit.
    current.reference_url = REFS[0]
    current.reference_urls = json.dumps([*REFS[:2], OTHER_SOURCE])
    assert data["remix_parent_generation_id"] == derived.id
    assert await image_gen._launch_session_generation(
        source_message=call.message, state=state, session=launch.session, db_user=launch.user,
        image_session=current, prompt=SECRET, action_type=ImageGenerationAction.remix,
        reference_url=[*REFS[:2], OTHER_SOURCE], parent_generation_id=derived.id,
        source_feed_gen_id=77, feed_change_request="make the coat blue", launching_text="launch", queued_text="queued",
    )
    assert wire[0]["body"]["params"]["image_urls"] == [OTHER_SOURCE, *REFS[:2]]
    context = generated[-1].input_params[prompt_core.FEED_REMIX_CONTEXT_KEY]
    assert context["scene_generation_id"] == derived.id
    assert context["source_image_url"] == OTHER_SOURCE
    assert SECRET not in str(wire)
    return SimpleNamespace(launch=launch, records=records, generated=generated, derived=derived, current=current)


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("aliases", [False, True])
async def test_derived_scene_collector_at_cap_clear_and_next_repeat(derived_repeat, wire, monkeypatch, model, aliases):
    from bot.handlers import repeat_references

    setup = derived_repeat
    launch = setup.launch
    if aliases:
        monkeypatch.setattr(miniapp_routes.settings, "WEB_PUBLIC_URL", "https://app.example.test")
        source_alias = f"https://app.example.test/api/v1/feed/77/display.webp?index=0&output_id={feed_media.feed_source_output_id(launch.source, SOURCE)}"
        derived_alias = f"https://app.example.test/api/v1/feed/88/preview.webp?index=0&output_id={feed_media.feed_source_output_id(setup.derived, OTHER_SOURCE)}"
        setup.current.reference_urls = json.dumps([*REFS[:2], OTHER_SOURCE, SOURCE, source_alias, derived_alias])
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value=REFS[2]))
    state, data = mutable_state()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), data="regen:image:100")
    await repeat_references._regen_repeat_interceptor(call, launch.session, state, launch.user, AsyncMock())
    assert data["repeat_reference_count"] == 3
    message = SimpleNamespace(photo=[SimpleNamespace(file_id="third-user-photo", file_size=10)], answer=AsyncMock())
    await repeat_references._collect_repeat_reference(message, state, launch.session, launch.user, AsyncMock())
    assert data["repeat_reference_count"] == 4
    assert data["repeat_new_reference_file_ids"] == ["third-user-photo"]
    await repeat_references._repeat_refs_run(call, launch.session, state, launch.user, AsyncMock())
    assert len(wire) == 2
    assert wire[-1]["body"]["params"]["image_urls"] == [OTHER_SOURCE, *REFS]
    assert_scene_first_edit(wire[-1]["body"]["params"]["prompt"])
    assert wire[-1]["body"]["params"]["prompt"].endswith("make the coat blue")
    call.data = f"regen:image:{setup.generated[-1].id}"
    await repeat_references._regen_repeat_interceptor(call, launch.session, state, launch.user, AsyncMock())
    assert data["repeat_reference_count"] == 4
    await repeat_references._repeat_refs_run(call, launch.session, state, launch.user, AsyncMock())
    assert len(wire) == 3
    assert wire[-1]["body"]["params"]["image_urls"] == [OTHER_SOURCE, *REFS]
    assert_scene_first_edit(wire[-1]["body"]["params"]["prompt"])
    call.data = f"regen:image:{setup.generated[-1].id}"
    await repeat_references._regen_repeat_interceptor(call, launch.session, state, launch.user, AsyncMock())
    # Clear must remove an expired user input rather than require it to be available.
    monkeypatch.setattr(image_gen, "public_url_is_available", lambda url: url != REFS[0])
    await repeat_references._repeat_refs_clear(call, state, launch.session, launch.user)
    assert data["repeat_reference_count"] == 1
    assert data["repeat_base_reference_urls"] == [OTHER_SOURCE]
    await repeat_references._repeat_refs_run(call, launch.session, state, launch.user, AsyncMock())
    assert len(wire) == 4
    assert wire[-1]["body"]["params"]["image_urls"] == [OTHER_SOURCE]
    assert "EXCLUSIVE source" not in wire[-1]["body"]["params"]["prompt"]
    assert SECRET not in str(wire)


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("stage", ["begin", "add", "clear", "run"])
@pytest.mark.parametrize("failure", ["missing_scene", "unowned_scene", "forged_scene", "expired_scene"])
async def test_derived_scene_admission_rejects_before_collection_or_session_mutation(
    derived_repeat, wire, monkeypatch, model, stage, failure,
):
    from bot.handlers import repeat_references

    setup = derived_repeat
    launch = setup.launch
    state, data = mutable_state()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), data="regen:image:100")
    if stage != "begin":
        await repeat_references._regen_repeat_interceptor(call, launch.session, state, launch.user, AsyncMock())
    if failure == "missing_scene":
        setup.records.pop(88)
    elif failure == "unowned_scene":
        setup.derived.user_id = 999
    elif failure == "forged_scene":
        setup.generated[0].input_params[prompt_core.FEED_REMIX_CONTEXT_KEY]["scene_generation_id"] = 555
    else:
        monkeypatch.setattr(image_gen, "public_url_is_available", lambda url: url != OTHER_SOURCE)
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value=REFS[0]))
    before = dict(data)
    sessions_before = list(launch.created_sessions)
    repo.archive_active_image_sessions.reset_mock()
    repo.charge_image_generation.reset_mock()
    repo.create_generation.reset_mock()
    if stage == "begin":
        await repeat_references._regen_repeat_interceptor(call, launch.session, state, launch.user, AsyncMock())
    elif stage == "add":
        await repeat_references._collect_repeat_reference(
            SimpleNamespace(photo=[SimpleNamespace(file_id="existing-user-alias", file_size=10)], answer=AsyncMock()),
            state, launch.session, launch.user, AsyncMock(),
        )
    elif stage == "clear":
        await repeat_references._repeat_refs_clear(call, state, launch.session, launch.user)
    else:
        await repeat_references._repeat_refs_run(call, launch.session, state, launch.user, AsyncMock())
    assert data == before
    assert launch.created_sessions == sessions_before
    assert len(wire) == 1
    repo.archive_active_image_sessions.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    repo.create_generation.assert_not_awaited()


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("stage", ["add", "run"])
async def test_derived_scene_expected_identity_availability_still_required(derived_repeat, wire, monkeypatch, model, stage):
    from bot.handlers import repeat_references

    setup = derived_repeat
    launch = setup.launch
    state, data = mutable_state()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), data="regen:image:100")
    await repeat_references._regen_repeat_interceptor(call, launch.session, state, launch.user, AsyncMock())
    monkeypatch.setattr(image_gen, "public_url_is_available", lambda url: url != REFS[0])
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value=REFS[1]))
    before = dict(data)
    sessions_before = list(launch.created_sessions)
    repo.archive_active_image_sessions.reset_mock()
    repo.charge_image_generation.reset_mock()
    if stage == "add":
        await repeat_references._collect_repeat_reference(
            SimpleNamespace(photo=[SimpleNamespace(file_id="existing-user-alias", file_size=10)], answer=AsyncMock()),
            state, launch.session, launch.user, AsyncMock(),
        )
    else:
        await repeat_references._repeat_refs_run(call, launch.session, state, launch.user, AsyncMock())
    assert data == before
    assert launch.created_sessions == sessions_before
    assert len(wire) == 1
    repo.archive_active_image_sessions.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
