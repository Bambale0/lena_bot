from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts import set_qwen_route as command


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.asyncio
async def test_ops_command_uses_explicit_operator_without_printing_it(monkeypatch, capsys):
    route = SimpleNamespace(
        mode="image", primary_provider="kie", backup_provider="neironych"
    )
    setter = AsyncMock(return_value=route)
    monkeypatch.setattr(command, "set_qwen_route", setter)
    monkeypatch.setattr(
        command,
        "AsyncSessionLocal",
        lambda: _SessionContext(SimpleNamespace()),
    )

    assert await command.run(
        mode="image",
        primary="kie",
        backup="neironych",
        operator_identity="codex-for-Bambale0-20261025",
    ) == 0
    assert setter.await_args.kwargs == {
        "admin_tg_id": None,
        "operator_identity": "codex-for-Bambale0-20261025",
        "source": "ops",
    }
    output = capsys.readouterr().out
    assert "Qwen image route: kie -> neironych" in output
    assert "codex-for-Bambale0-20261025" not in output


def test_ops_command_requires_explicit_operator(monkeypatch):
    monkeypatch.setattr(
        command.sys,
        "argv",
        ["set_qwen_route.py", "image", "kie", "neironych"],
    )

    with pytest.raises(SystemExit) as error:
        command.parse_args()

    assert error.value.code == 2
