from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OWNED_PREFIXES = (
    "menu:",
    "img",
    "vpar",
    "vid_",
    "music",
    "feed:",
    "gen:",
    "prompts:",
    "balance",
    "start:",
    "sticker",
    "setlang:",
    "p2p:",
    "regen:",
    "ref:",
    "topup:",
    "promo:",
    "help:",
    "faq:",
)

IGNORED_EXACT = {"noop"}
IGNORED_PREFIXES = {"pay:", "admin:"}


def py_files(folder: str) -> list[Path]:
    return sorted((ROOT / folder).rglob("*.py"))


def collect_keyboard_callbacks() -> set[str]:
    callbacks: set[str] = set()
    for path in py_files("bot/keyboards") + py_files("bot/ui"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            raise AssertionError(f"Syntax error in {path}")
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "callback_data":
                value = node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    callbacks.add(value.value)
                elif isinstance(value, ast.JoinedStr):
                    prefix = ""
                    for part in value.values:
                        if isinstance(part, ast.Constant) and isinstance(part.value, str):
                            prefix += part.value
                        else:
                            break
                    if prefix:
                        callbacks.add(prefix)
    return callbacks


def collect_handler_patterns() -> set[str]:
    patterns: set[str] = set()
    for path in py_files("bot/handlers"):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r'F\.data\s*==\s*["\']([^"\']+)["\']', text):
            patterns.add(m.group(1))
        for m in re.finditer(r'F\.data\.startswith\(["\']([^"\']+)["\']\)', text):
            patterns.add(m.group(1))
        for m in re.finditer(r'Command\(["\']([^"\']+)["\']\)', text):
            cmd = m.group(1)
            patterns.add(cmd)
            patterns.add(cmd + " ")
    return patterns


def covered(callback: str, patterns: set[str]) -> bool:
    if callback in IGNORED_EXACT:
        return True
    if any(callback.startswith(p) for p in IGNORED_PREFIXES):
        return True
    # callback — prefix handler-а (напр. "regen:" покрыт handler "regen:image:")
    if any(p.startswith(callback) for p in patterns):
        return True
    # handler покрывает callback (напр. "feed:next:" покрывает "feed:next:1")
    return any(callback == p or callback.startswith(p) for p in patterns)


def test_keyboard_callbacks_have_handlers():
    callbacks = {
        cb for cb in collect_keyboard_callbacks()
        if cb.startswith(OWNED_PREFIXES)
    }
    patterns = collect_handler_patterns()
    missing = sorted(cb for cb in callbacks if not covered(cb, patterns))
    assert not missing, (
        "callback_data bez handlera:\n"
        + "\n".join(missing)
        + "\n\nHandlers:\n"
        + "\n".join(sorted(patterns))
    )


def test_no_duplicate_functions_in_keyboards_models():
    path = ROOT / "bot/keyboards/models.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: dict[str, int] = {}
    duplicates = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names[node.name] = names.get(node.name, 0) + 1
            if names[node.name] == 2:
                duplicates.append(node.name)
    assert not duplicates, "Duble funkcij v bot/keyboards/models.py: " + ", ".join(duplicates)


def test_feed_kb_smoke():
    """Smoke test for feed keyboards."""
    from bot.keyboards.feed import feed_card_kb, empty_feed_kb
    kb1 = empty_feed_kb()
    kb2 = feed_card_kb(gen_id=1, index=0, source="feed", has_next=False)
    assert kb1 is not None
    assert kb2 is not None