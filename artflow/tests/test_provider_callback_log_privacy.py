from __future__ import annotations

import logging

import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [main.settings.KIE_WEBHOOK_PATH, main.settings.MIDJOURNEY_WEBHOOK_PATH,
                                  "/webhook/kie/suno-voice", "/webhook/kie/music"])
async def test_invalid_callbacks_do_not_log_prompt_media_or_credentials(monkeypatch, caplog, path):
    monkeypatch.setattr(main.settings, "KIE_WEBHOOK_SECRET", "")
    monkeypatch.setattr(main.settings, "MIDJOURNEY_WEBHOOK_SECRET", "audit-webhook-test")
    payload = {"prompt": "PRIVATE_PROMPT_9e3b", "url": "https://private.example/media?token=PRIVATE_TOKEN_9e3b"}
    with caplog.at_level(logging.WARNING):
        async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
            response = await client.post(path, params={"secret": "audit-webhook-test"} if path == main.settings.MIDJOURNEY_WEBHOOK_PATH else None, json=payload)
    assert response.status_code == 200
    assert "PRIVATE_PROMPT_9e3b" not in caplog.text
    assert "private.example" not in caplog.text
    assert "PRIVATE_TOKEN_9e3b" not in caplog.text
    assert caplog.records, "Missing callback diagnostic"


def test_structured_callback_diagnostic_rejects_untrusted_ids_and_exception_text(caplog):
    from core.provider_logging import callback_anomaly

    with caplog.at_level(logging.WARNING):
        callback_anomaly(logging.getLogger("privacy-test"), "kie", "download_failed",
                         task_id="https://private.example/id?token=SECRET_TEST_VALUE",
                         status="done\nFORGED_LOG", error=RuntimeError("PRIVATE_PROMPT https://private.example/media"))
    assert "private.example" not in caplog.text
    assert "SECRET_TEST_VALUE" not in caplog.text
    assert "PRIVATE_PROMPT" not in caplog.text
    assert "FORGED_LOG" not in caplog.text
    record = caplog.records[-1]
    assert record.callback_task_id == "invalid"
    assert record.callback_error_type == "RuntimeError"


def test_callback_log_calls_do_not_accept_raw_payload_urls_or_provider_messages():
    import ast
    from pathlib import Path

    tree = ast.parse(Path(main.__file__).read_text())
    forbidden = {"payload", "data", "url", "result_url", "normalized_msg", "err"}
    for fn in tree.body:
        if not isinstance(fn, ast.AsyncFunctionDef) or "webhook" not in fn.name:
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not isinstance(node.func.value, ast.Name) or node.func.value.id != "logger":
                continue
            args = [arg.id for arg in node.args[1:] if isinstance(arg, ast.Name)]
            assert not forbidden.intersection(args), (fn.name, node.lineno, args)


@pytest.mark.asyncio
async def test_unknown_callback_id_cannot_smuggle_media_url_into_logs(monkeypatch, caplog):
    from unittest.mock import AsyncMock, MagicMock

    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=object())
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: context)
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(main.repo, "get_generation_by_task_id", lookup)
    monkeypatch.setattr(main.settings, "KIE_WEBHOOK_SECRET", "")
    identifier = "https://private.example/media?token=SECRET_LOG_INJECTION"
    with caplog.at_level(logging.WARNING):
        async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
            response = await client.post(main.settings.KIE_WEBHOOK_PATH, json={"data": {"taskId": identifier}})
    assert response.status_code == 200
    assert lookup.await_args_list[0].args[1] == identifier  # Lookup semantics are unchanged.
    assert "private.example" not in caplog.text
    assert "SECRET_LOG_INJECTION" not in caplog.text
    assert "invalid" in caplog.text
