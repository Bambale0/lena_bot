from __future__ import annotations

import json
from unittest.mock import Mock

import bot_tester


def test_tg_serializes_nested_params(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps({"ok": True}).encode()

    def fake_urlopen(req, timeout):
        captured["body"] = req.data.decode()
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(bot_tester.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(bot_tester, "TOKEN", "token")

    assert bot_tester.tg("sendMessage", reply_markup={"inline_keyboard": []}) == {"ok": True}
    assert "reply_markup=%7B%22inline_keyboard%22" in captured["body"]


def test_tg_returns_error_dict_on_network_error(monkeypatch) -> None:
    monkeypatch.setattr(bot_tester.urllib.request, "urlopen", Mock(side_effect=RuntimeError("offline")))
    monkeypatch.setattr(bot_tester, "TOKEN", "token")
    assert bot_tester.tg("getMe")["ok"] is False
