from __future__ import annotations

from types import SimpleNamespace

from api.prompt_privacy import (
    hide_feed_prompt_payload,
    hide_generation_prompt_payload,
    hide_prompt_card_payload,
    install_miniapp_prompt_privacy,
)


def test_hide_generation_prompt_payload_dict() -> None:
    payload = {
        "prompt": "secret prompt",
        "prompt_hidden": False,
        "prompt_actions_allowed": True,
        "session_last_prompt": "secret again",
        "base_prompt": "base secret",
        "last_prompt": "last secret",
    }

    assert hide_generation_prompt_payload(payload) == {
        "prompt": "",
        "prompt_hidden": True,
        "prompt_actions_allowed": False,
        "session_last_prompt": None,
        "base_prompt": None,
        "last_prompt": None,
    }


def test_hide_generation_prompt_payload_object() -> None:
    payload = SimpleNamespace(
        prompt="secret prompt",
        prompt_hidden=False,
        prompt_actions_allowed=True,
        session_last_prompt="secret again",
    )

    hidden = hide_generation_prompt_payload(payload)

    assert hidden.prompt == ""
    assert hidden.prompt_hidden is True
    assert hidden.prompt_actions_allowed is False
    assert hidden.session_last_prompt is None


def test_hide_feed_prompt_payload() -> None:
    payload = {"id": 1, "prompt": "public leak", "prompt_visibility": "excerpt"}

    assert hide_feed_prompt_payload(payload) == {
        "id": 1,
        "prompt": "",
        "prompt_visibility": "hidden",
    }


def test_hide_prompt_card_payload_keeps_prompt_id_usable() -> None:
    payload = {"id": 44, "title": "Portrait", "prompt_text": "secret recipe"}

    assert hide_prompt_card_payload(payload) == {
        "id": 44,
        "title": "Portrait",
        "prompt_text": "",
        "prompt_hidden": True,
        "prompt_visibility": "hidden",
    }


def test_install_miniapp_prompt_privacy_wraps_serializers() -> None:
    routes = SimpleNamespace(
        _gen_out=lambda _gen: SimpleNamespace(prompt="secret", prompt_hidden=False, prompt_actions_allowed=True),
        _feed_card_out=lambda _card, _user: {"prompt": "leak", "prompt_visibility": "excerpt"},
        _prompt_out=lambda _prompt: {"id": 7, "prompt_text": "secret prompt"},
    )

    install_miniapp_prompt_privacy(routes)

    generation = routes._gen_out(object())
    feed = routes._feed_card_out(object(), object())
    prompt = routes._prompt_out(object())

    assert generation.prompt == ""
    assert generation.prompt_hidden is True
    assert generation.prompt_actions_allowed is False
    assert feed["prompt"] == ""
    assert feed["prompt_visibility"] == "hidden"
    assert prompt["prompt_text"] == ""
    assert prompt["prompt_hidden"] is True
