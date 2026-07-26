from __future__ import annotations

import pytest

from api import midjourney_full_service as mj
from api.midjourney_full_service import (
    BlendDimensions,
    MidjourneyAnimateMode,
    MidjourneyBot,
    MidjourneyChangeAction,
    MidjourneyMotion,
    MidjourneySpeed,
    MidjourneyTaskStatus,
    MidjourneyVideoMode,
)


@pytest.mark.asyncio
async def test_imagine_exact_payload(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"code": 1, "result": "imagine_task"}

    monkeypatch.setattr(mj.comet_client, "post", fake_post)

    task_id = await mj.imagine(
        "A cat --ar 16:9 --v 8",
        bot=MidjourneyBot.NIJI,
        speed=MidjourneySpeed.TURBO,
        base64_array=["https://example.test/ref.png"],
        state="user:42",
    )

    assert task_id == "imagine_task"
    assert calls == [
        (
            "/mj-turbo/mj/submit/imagine",
            {
                "botType": "NIJI_JOURNEY",
                "prompt": "A cat --ar 16:9 --v 8",
                "accountFilter": {"modes": ["TURBO"]},
                "base64Array": ["https://example.test/ref.png"],
                "state": "user:42",
            },
        )
    ]


@pytest.mark.asyncio
async def test_action_exact_payload(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"code": 1, "result": "action_task"}

    monkeypatch.setattr(mj.comet_client, "post", fake_post)

    await mj.action(
        "parent_task",
        "MJ::JOB::upsample::1::abc",
        enable_remix=True,
        state="state",
    )

    assert calls == [
        (
            "/mj/submit/action",
            {
                "taskId": "parent_task",
                "customId": "MJ::JOB::upsample::1::abc",
                "enableRemix": True,
                "state": "state",
            },
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "index", "expected"),
    [
        (MidjourneyChangeAction.UPSCALE, 1, {"action": "UPSCALE", "index": 1}),
        (MidjourneyChangeAction.VARIATION, 4, {"action": "VARIATION", "index": 4}),
        (MidjourneyChangeAction.REROLL, None, {"action": "REROLL"}),
    ],
)
async def test_change_exact_payload(monkeypatch, action, index, expected) -> None:
    calls: list[dict] = []

    async def fake_post(path: str, payload: dict) -> dict:
        assert path == "/mj/submit/change"
        calls.append(payload)
        return {"code": 1, "result": "changed"}

    monkeypatch.setattr(mj.comet_client, "post", fake_post)

    await mj.change("parent", action, index=index)

    assert calls == [{**expected, "taskId": "parent"}]


@pytest.mark.asyncio
async def test_change_validates_index_before_provider(monkeypatch) -> None:
    async def forbidden_post(path: str, payload: dict) -> dict:
        raise AssertionError("invalid request must not reach provider")

    monkeypatch.setattr(mj.comet_client, "post", forbidden_post)

    with pytest.raises(ValueError, match="index must be 1-4"):
        await mj.change("parent", "UPSCALE", index=5)


@pytest.mark.asyncio
async def test_modal_requires_prompt_or_mask(monkeypatch) -> None:
    async def forbidden_post(path: str, payload: dict) -> dict:
        raise AssertionError("invalid request must not reach provider")

    monkeypatch.setattr(mj.comet_client, "post", forbidden_post)

    with pytest.raises(ValueError, match="requires prompt or mask"):
        await mj.modal("parent")


@pytest.mark.asyncio
async def test_modal_exact_payload(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"code": 1, "result": "modal_task"}

    monkeypatch.setattr(mj.comet_client, "post", fake_post)

    await mj.modal(
        "parent",
        prompt="Replace the sky",
        mask_base64="data:image/png;base64,AAAA",
    )

    assert calls == [
        (
            "/mj/submit/modal",
            {
                "taskId": "parent",
                "prompt": "Replace the sky",
                "maskBase64": "data:image/png;base64,AAAA",
            },
        )
    ]


@pytest.mark.asyncio
async def test_blend_exact_payload(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"code": 1, "result": "blend_task"}

    monkeypatch.setattr(mj.comet_client, "post", fake_post)

    await mj.blend(
        [
            "data:image/png;base64,AAAA",
            "https://example.test/second.jpg",
        ],
        dimensions=BlendDimensions.LANDSCAPE,
        bot=MidjourneyBot.MIDJOURNEY,
        prompt="Combine their visual language",
    )

    assert calls == [
        (
            "/mj/submit/blend",
            {
                "botType": "MID_JOURNEY",
                "base64Array": [
                    "data:image/png;base64,AAAA",
                    "https://example.test/second.jpg",
                ],
                "dimensions": "LANDSCAPE",
                "prompt": "Combine their visual language",
            },
        )
    ]


@pytest.mark.asyncio
async def test_blend_validates_image_count(monkeypatch) -> None:
    async def forbidden_post(path: str, payload: dict) -> dict:
        raise AssertionError("invalid request must not reach provider")

    monkeypatch.setattr(mj.comet_client, "post", forbidden_post)

    with pytest.raises(ValueError, match="2-5 images"):
        await mj.blend(["https://example.test/only.png"])


@pytest.mark.asyncio
async def test_describe_requires_exactly_one_input(monkeypatch) -> None:
    async def forbidden_post(path: str, payload: dict) -> dict:
        raise AssertionError("invalid request must not reach provider")

    monkeypatch.setattr(mj.comet_client, "post", forbidden_post)

    with pytest.raises(ValueError, match="exactly one"):
        await mj.describe()
    with pytest.raises(ValueError, match="exactly one"):
        await mj.describe(
            base64_image="data:image/png;base64,AAAA",
            image_url="https://example.test/ref.png",
        )


@pytest.mark.asyncio
async def test_describe_url_exact_payload(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"code": 1, "result": "describe_task"}

    monkeypatch.setattr(mj.comet_client, "post", fake_post)

    await mj.describe(image_url="https://example.test/ref.png")

    assert calls == [
        (
            "/mj/submit/describe",
            {"botType": "MID_JOURNEY", "link": "https://example.test/ref.png"},
        )
    ]


@pytest.mark.asyncio
async def test_editor_forwards_native_payload_unchanged(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"code": 1, "result": "editor_task"}

    monkeypatch.setattr(mj.comet_client, "post", fake_post)

    payload = {
        "prompt": "Remove the chair",
        "maskBase64": "data:image/png;base64,AAAA",
        "originals": ["data:image/png;base64,BBBB"],
        "transparent": True,
        "providerFutureField": {"kept": True},
    }
    await mj.submit_editor(payload)

    assert calls == [("/mj/submit/edits", payload)]


@pytest.mark.asyncio
async def test_video_exact_current_payload(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"code": 1, "result": "video_task"}

    monkeypatch.setattr(mj.comet_client, "post", fake_post)

    await mj.submit_video(
        "https://cdn.midjourney.com/image.png",
        prompt="add a dog",
        video_type="vid_1.1_i2v_480",
        mode=MidjourneyVideoMode.FAST,
        animate_mode=MidjourneyAnimateMode.MANUAL,
        motion=MidjourneyMotion.LOW,
    )

    assert calls == [
        (
            "/mj/submit/video",
            {
                "prompt": "https://cdn.midjourney.com/image.png add a dog",
                "videoType": "vid_1.1_i2v_480",
                "mode": "fast",
                "animateMode": "manual",
                "motion": "low",
            },
        )
    ]


@pytest.mark.asyncio
async def test_video_rejects_unknown_video_type(monkeypatch) -> None:
    async def forbidden_post(path: str, payload: dict) -> dict:
        raise AssertionError("invalid request must not reach provider")

    monkeypatch.setattr(mj.comet_client, "post", forbidden_post)

    with pytest.raises(ValueError, match="video_type"):
        await mj.submit_video(
            "https://example.test/image.png",
            video_type="unknown",
        )


@pytest.mark.asyncio
async def test_fetch_parses_all_current_statuses_and_buttons(monkeypatch) -> None:
    async def fake_get(path: str) -> dict:
        assert path == "/mj/task/task_1/fetch"
        return {
            "id": "task_1",
            "action": "IMAGINE",
            "status": "SUBMITTED",
            "progress": "10%",
            "prompt": "Cat",
            "imageUrl": "",
            "videoUrl": "",
            "buttons": [
                {
                    "customId": "MJ::JOB::variation::1::abc",
                    "label": "V1",
                    "emoji": "",
                    "type": 2,
                    "style": 2,
                }
            ],
            "properties": {"finalPrompt": "Cat --v 8"},
        }

    monkeypatch.setattr(mj.comet_client, "get", fake_get)

    task = await mj.fetch_task("task_1")

    assert task.status == MidjourneyTaskStatus.SUBMITTED
    assert task.buttons[0].custom_id == "MJ::JOB::variation::1::abc"


@pytest.mark.asyncio
async def test_list_by_condition_accepts_wrapped_response(monkeypatch) -> None:
    async def fake_post(path: str, payload: dict) -> dict:
        assert path == "/mj/task/list-by-condition"
        assert payload == {"ids": ["a", "b"]}
        return {
            "data": [
                {"id": "a", "status": "SUCCESS", "imageUrl": "https://x/a.png"},
                {"id": "b", "status": "CANCEL", "failReason": "cancelled"},
            ]
        }

    monkeypatch.setattr(mj.comet_client, "post", fake_post)

    tasks = await mj.list_by_condition(["a", "b"])

    assert [task.status for task in tasks] == [
        MidjourneyTaskStatus.SUCCESS,
        MidjourneyTaskStatus.CANCEL,
    ]


@pytest.mark.asyncio
async def test_poll_image_and_video_terminal_behavior(monkeypatch) -> None:
    tasks = [
        mj.MidjourneyTask(
            task_id="image",
            status=MidjourneyTaskStatus.SUCCESS,
            image_url="https://example.test/image.png",
        ),
        mj.MidjourneyTask(
            task_id="video",
            status=MidjourneyTaskStatus.SUCCESS,
            video_url="https://example.test/video.mp4",
        ),
    ]

    async def fake_fetch(task_id: str):
        return tasks.pop(0)

    monkeypatch.setattr(mj, "fetch_task", fake_fetch)

    assert await mj.poll_image("image") == "https://example.test/image.png"
    assert await mj.poll_video("video") == "https://example.test/video.mp4"
