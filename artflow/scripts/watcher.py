#!/usr/bin/env python3
"""
Hot-swap watcher: monitors project source files and restarts
the artflow-webhook systemd service on any change.

Usage:
    python scripts/watcher.py [--service artflow-webhook] [--debounce 2.0]
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

from watchdog.events import (
    FileClosedEvent,
    FileCreatedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers.polling import PollingObserver as Observer

_TRIGGER_TYPES = (FileModifiedEvent, FileCreatedEvent, FileMovedEvent, FileClosedEvent)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [watcher] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("watcher")

WATCH_DIRS = ["bot", "db", "api", "core", "payments"]
WATCH_ROOT_FILES = {".env", "requirements.txt"}  # files in project root to watch directly
WATCH_EXTENSIONS = {".py", ".env", ".toml"}


class RestartHandler(FileSystemEventHandler):
    def __init__(self, service: str, debounce: float) -> None:
        self._service = service
        self._debounce = debounce
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if not isinstance(event, _TRIGGER_TYPES):
            return
        path = Path(str(event.src_path))
        # always trigger on root-level watched files (e.g. .env)
        if path.name not in WATCH_ROOT_FILES and path.suffix not in WATCH_EXTENSIONS:
            return
        # skip __pycache__ and other dot-dirs
        if any(part.startswith("__pycache__") for part in path.parts):
            return

        log.info("Changed: %s (%s)", path, event.event_type)
        self._schedule_restart()

    def _schedule_restart(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce, self._restart)
            self._timer.daemon = True
            self._timer.start()

    def _restart(self) -> None:
        log.info("Restarting %s ...", self._service)
        try:
            result = subprocess.run(
                ["systemctl", "restart", self._service],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                log.info("Restarted %s OK", self._service)
            else:
                log.error("systemctl restart failed: %s", result.stderr.strip())
        except Exception as e:
            log.error("Failed to restart service: %s", e)


PIDFILE = Path("/tmp/artflow-watcher.pid")


def _acquire_lock() -> None:
    """Kill any previous watcher instance and write own PID."""
    if PIDFILE.exists():
        try:
            old_pid = int(PIDFILE.read_text().strip())
            os.kill(old_pid, signal.SIGTERM)
            log.info("Terminated previous watcher instance (pid=%s)", old_pid)
        except (ValueError, ProcessLookupError, PermissionError):
            pass
    PIDFILE.write_text(str(os.getpid()))


def _release_lock() -> None:
    try:
        if PIDFILE.exists() and PIDFILE.read_text().strip() == str(os.getpid()):
            PIDFILE.unlink()
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Artflow hot-swap watcher")
    parser.add_argument("--service", default="artflow-webhook", help="systemd service name")
    parser.add_argument("--debounce", type=float, default=2.0, help="seconds to wait after last change")
    args = parser.parse_args()

    _acquire_lock()

    root = Path(__file__).resolve().parent.parent
    handler = RestartHandler(service=args.service, debounce=args.debounce)
    observer = Observer()

    watched = []
    # Watch project root non-recursively for .env and similar
    observer.schedule(handler, str(root), recursive=False)
    watched.append(f"{root}/ (root, non-recursive)")

    for d in WATCH_DIRS:
        watch_path = root / d
        if watch_path.exists():
            observer.schedule(handler, str(watch_path), recursive=True)
            watched.append(str(watch_path))

    if not watched:
        log.error("No watch directories found under %s", root)
        sys.exit(1)

    log.info("Watching: %s", ", ".join(watched))
    log.info("Service:  %s  |  Debounce: %.1fs", args.service, args.debounce)

    observer.start()
    try:
        while observer.is_alive():
            observer.join(timeout=1)
    except KeyboardInterrupt:
        log.info("Interrupted, stopping...")
    finally:
        observer.stop()
        observer.join()
        _release_lock()


if __name__ == "__main__":
    main()
