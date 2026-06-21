from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile
from sqlalchemy.engine import make_url

from core.config import settings

logger = logging.getLogger(__name__)

STATE_PATH = Path("data/db_backup_state.json")


class DatabaseBackupError(RuntimeError):
    pass


@dataclass(slots=True)
class DatabaseBackup:
    path: Path
    created_at: datetime
    size_bytes: int


def _read_state_sync() -> dict[str, str]:
    if not STATE_PATH.exists():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text())
    except Exception:
        logger.warning("Failed to read DB backup state; resetting")
        return {}
    return data if isinstance(data, dict) else {}


def _write_state_sync(state: dict[str, str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2))


async def _read_state() -> dict[str, str]:
    return await asyncio.to_thread(_read_state_sync)


async def _write_state(state: dict[str, str]) -> None:
    await asyncio.to_thread(_write_state_sync, state)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def _safe_error_text(exc: Exception) -> str:
    text = str(exc).strip().replace(settings.DATABASE_URL, "<DATABASE_URL>")
    if not text:
        return exc.__class__.__name__
    return text[:900]


def _backup_path(created_at: datetime) -> Path:
    backup_dir = Path(settings.DB_BACKUP_DIR)
    stamp = created_at.astimezone(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return backup_dir / f"artflow_db_{stamp}.dump"


def _pg_dump_command(database_url: str, output_path: Path) -> tuple[list[str], dict[str, str]]:
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise DatabaseBackupError(f"Unsupported database backend for pg_dump: {url.get_backend_name()}")
    if not url.database:
        raise DatabaseBackupError("DATABASE_URL does not contain a database name")

    env = os.environ.copy()
    env["PGDATABASE"] = url.database
    if url.host:
        env["PGHOST"] = url.host
    if url.port:
        env["PGPORT"] = str(url.port)
    if url.username:
        env["PGUSER"] = url.username
    password = url.password
    if password:
        env["PGPASSWORD"] = password
    sslmode = url.query.get("sslmode")
    if sslmode:
        env["PGSSLMODE"] = str(sslmode)

    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--file",
        str(output_path),
    ]
    return command, env


async def create_database_backup() -> DatabaseBackup:
    created_at = datetime.now(timezone.utc)
    path = _backup_path(created_at)
    path.parent.mkdir(parents=True, exist_ok=True)

    command, env = _pg_dump_command(settings.DATABASE_URL, path)
    pg_dump_path = shutil.which(command[0])
    if not pg_dump_path:
        raise DatabaseBackupError("pg_dump is not installed")
    command[0] = pg_dump_path

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    _stdout, stderr = await process.communicate()
    if process.returncode != 0:
        path.unlink(missing_ok=True)
        error = stderr.decode("utf-8", errors="replace").strip()
        raise DatabaseBackupError(f"pg_dump failed with exit code {process.returncode}: {error[:900]}")
    if not path.exists() or path.stat().st_size <= 0:
        path.unlink(missing_ok=True)
        raise DatabaseBackupError("pg_dump produced an empty backup file")
    return DatabaseBackup(path=path, created_at=created_at, size_bytes=path.stat().st_size)


def cleanup_old_backups() -> None:
    keep_last = max(1, int(settings.DB_BACKUP_KEEP_LAST or 1))
    backup_dir = Path(settings.DB_BACKUP_DIR)
    backups = sorted(backup_dir.glob("artflow_db_*.dump"), key=lambda item: item.stat().st_mtime, reverse=True)
    for old_backup in backups[keep_last:]:
        try:
            old_backup.unlink()
        except Exception as exc:
            logger.warning("Failed to remove old DB backup %s: %s", old_backup, exc)


async def send_database_backup_to_admins(bot: Bot) -> int:
    admin_ids = [int(admin_id) for admin_id in settings.ADMIN_IDS or []]
    if not admin_ids:
        logger.info("DB backup skipped: ADMIN_IDS is empty")
        return 0

    backup = await create_database_backup()
    caption = (
        "🗄 <b>Резервная копия БД</b>\n"
        f"Время UTC: <code>{backup.created_at.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
        f"Размер: <code>{_format_size(backup.size_bytes)}</code>"
    )

    sent = 0
    for admin_id in admin_ids:
        try:
            await bot.send_document(
                chat_id=admin_id,
                document=FSInputFile(backup.path, filename=backup.path.name),
                caption=caption,
            )
            sent += 1
        except Exception as exc:
            logger.warning("Failed to send DB backup to admin %s: %s", admin_id, exc)

    await asyncio.to_thread(cleanup_old_backups)
    if sent == 0:
        raise DatabaseBackupError("Failed to send DB backup to any admin chat")
    return sent


async def _seconds_until_next_attempt(interval_seconds: int) -> float:
    state = await _read_state()
    last_attempt = _parse_datetime(state.get("last_attempt_at"))
    if last_attempt is None:
        return 0.0
    elapsed = (datetime.now(timezone.utc) - last_attempt).total_seconds()
    return max(0.0, float(interval_seconds) - elapsed)


async def _mark_attempt(*, success: bool, sent: int = 0, error: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    state = await _read_state()
    state["last_attempt_at"] = now
    if success:
        state["last_sent_at"] = now
        state["last_sent_count"] = str(sent)
        state.pop("last_error", None)
    elif error:
        state["last_error"] = error
    await _write_state(state)


async def _notify_backup_failure(bot: Bot, exc: Exception) -> None:
    text = "⚠️ <b>Не удалось создать резервную копию БД</b>\n\n" + f"<code>{_safe_error_text(exc)}</code>"
    for admin_id in settings.ADMIN_IDS or []:
        try:
            await bot.send_message(int(admin_id), text)
        except Exception as send_exc:
            logger.warning("Failed to notify admin %s about DB backup failure: %s", admin_id, send_exc)


async def run_database_backup_scheduler(stop_event: asyncio.Event, bot: Bot) -> None:
    if not settings.DB_BACKUP_ENABLED:
        logger.info("DB backup scheduler disabled")
        return

    interval_seconds = max(60, int(settings.DB_BACKUP_INTERVAL_SECONDS or 21600))
    while not stop_event.is_set():
        try:
            delay = await _seconds_until_next_attempt(interval_seconds)
            if delay > 0:
                await asyncio.wait_for(stop_event.wait(), timeout=delay)
                continue
        except asyncio.TimeoutError:
            pass
        if stop_event.is_set():
            break

        try:
            sent = await send_database_backup_to_admins(bot)
            await _mark_attempt(success=True, sent=sent)
            logger.info("DB backup sent to %s admin chats", sent)
        except Exception as exc:
            logger.exception("DB backup scheduler error: %s", exc)
            await _mark_attempt(success=False, error=_safe_error_text(exc))
            await _notify_backup_failure(bot, exc)
