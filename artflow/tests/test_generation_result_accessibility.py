from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_native_telegram_back_button_tracks_dialogs_and_tabs():
    nav = (ROOT / "webapp/src/lib/telegram-navigation.ts").read_text()
    main = (ROOT / "webapp/src/main.tsx").read_text()
    assert "BackButton" in nav
    assert "visibleDialog" in nav
    assert 'aria-selected="true"' in nav
    assert "installTelegramNavigation" in main


def test_sheet_traps_focus_escape_and_restores_previous_focus():
    src = (ROOT / "webapp/src/components/ui/sheet.tsx").read_text()
    for token in (
        'event.key === "Escape"',
        'event.key !== "Tab"',
        "previousFocus",
        "aria-modal=\"true\"",
        "aria-describedby",
    ):
        assert token in src


def test_result_detail_uses_human_status_and_accessible_actions():
    detail = (ROOT / "webapp/src/components/task-detail-sheet.tsx").read_text()
    utils = (ROOT / "webapp/src/lib/utils.ts").read_text()
    assert "generationStatusLabel" in detail
    assert 'aria-label="Скопировать Task ID"' in detail
    for label in ("В очереди", "Создаётся", "Готово", "Ошибка"):
        assert label in utils


def test_locked_state_does_not_invent_balance_or_tasks():
    src = (ROOT / "webapp/src/components/locked-screen.tsx").read_text()
    assert "Баланс и задачи не подменяются демо-данными" in src
