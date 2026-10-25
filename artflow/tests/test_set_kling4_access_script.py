from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts import set_kling4_access as command


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.asyncio
async def test_ops_command_uses_shell_identity_without_printing_it(monkeypatch, capsys):
    setter = AsyncMock(return_value="public")
    monkeypatch.setattr(command, "set_kling4_access", setter)
    monkeypatch.setattr(command.getpass, "getuser", lambda: "release")
    monkeypatch.setattr(command.socket, "gethostname", lambda: "container-1")
    monkeypatch.setattr(
        command,
        "AsyncSessionLocal",
        lambda: _SessionContext(SimpleNamespace()),
    )

    assert await command.run(audience="public") == 0
    assert setter.await_args.kwargs == {
        "operator_identity": "release@container-1",
        "source": "ops",
    }
    output = capsys.readouterr().out
    assert "Kling 4 access policy: public" in output
    assert "release@container-1" not in output
