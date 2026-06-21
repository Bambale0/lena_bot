from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import FSInputFile

from core import db_backup_scheduler


def test_pg_dump_command_uses_env_for_credentials(tmp_path) -> None:
    output_path = tmp_path / "backup.dump"

    command, env = db_backup_scheduler._pg_dump_command(
        "postgresql+asyncpg://bot:secret@postgres:5432/artflow?sslmode=require",
        output_path,
    )

    assert command == [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--file",
        str(output_path),
    ]
    assert "secret" not in " ".join(command)
    assert env["PGHOST"] == "postgres"
    assert env["PGPORT"] == "5432"
    assert env["PGDATABASE"] == "artflow"
    assert env["PGUSER"] == "bot"
    assert env["PGPASSWORD"] == "secret"
    assert env["PGSSLMODE"] == "require"


@pytest.mark.asyncio
async def test_send_database_backup_to_admins_sends_document(monkeypatch, tmp_path) -> None:
    backup_path = tmp_path / "artflow_db_test.dump"
    backup_path.write_bytes(b"backup")
    backup = db_backup_scheduler.DatabaseBackup(
        path=backup_path,
        created_at=datetime(2026, 6, 17, 9, 0, tzinfo=timezone.utc),
        size_bytes=backup_path.stat().st_size,
    )
    bot = SimpleNamespace(send_document=AsyncMock())

    monkeypatch.setattr(db_backup_scheduler.settings, "ADMIN_IDS", [101, 202], raising=False)
    monkeypatch.setattr(db_backup_scheduler, "create_database_backup", AsyncMock(return_value=backup))
    monkeypatch.setattr(db_backup_scheduler, "cleanup_old_backups", lambda: None)

    sent = await db_backup_scheduler.send_database_backup_to_admins(bot)

    assert sent == 2
    assert bot.send_document.await_count == 2
    first_call = bot.send_document.await_args_list[0].kwargs
    assert first_call["chat_id"] == 101
    assert isinstance(first_call["document"], FSInputFile)
    assert "Резервная копия БД" in first_call["caption"]


@pytest.mark.asyncio
async def test_send_database_backup_raises_if_no_admin_received_file(monkeypatch, tmp_path) -> None:
    backup_path = tmp_path / "artflow_db_test.dump"
    backup_path.write_bytes(b"backup")
    backup = db_backup_scheduler.DatabaseBackup(
        path=backup_path,
        created_at=datetime(2026, 6, 17, 9, 0, tzinfo=timezone.utc),
        size_bytes=backup_path.stat().st_size,
    )
    bot = SimpleNamespace(send_document=AsyncMock(side_effect=RuntimeError("blocked")))

    monkeypatch.setattr(db_backup_scheduler.settings, "ADMIN_IDS", [101], raising=False)
    monkeypatch.setattr(db_backup_scheduler, "create_database_backup", AsyncMock(return_value=backup))
    monkeypatch.setattr(db_backup_scheduler, "cleanup_old_backups", lambda: None)

    with pytest.raises(db_backup_scheduler.DatabaseBackupError):
        await db_backup_scheduler.send_database_backup_to_admins(bot)
