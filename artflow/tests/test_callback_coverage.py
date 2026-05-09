from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "bot"

CRITICAL_CALLBACKS = {
    # main/menu
    "menu:image",
    "menu:video",
    "menu:music",
    "menu:prompts",
    "menu:history",
    "menu:balance",

    # image scenarios / dynamic settings
    "img_scn:fast",
    "img_scn:edit",
    "img_menu:advanced",
    "img_dyn:mode:nano-banana-pro",
    "img_dyn:ratio:nano-banana-pro",
    "img_dyn:count:nano-banana-pro",
    "img_dyn:enhance:nano-banana-pro",
    "img_dyn:continue:nano-banana-pro",

    # image settings / session
    "img_settings",
    "img_session:close",
    "img:photo2prompt",
    "img:cancel_prompt",

    # video params
    "vpar_next",
    "vpar_back",
    "vpar_dur:5",
    "vpar_ratio:16:9",
    "vpar_res:720p",

    # music
    "music:generate",
    "music:instrumental",
}

IGNORED_PREFIXES = {
    # external/payment/webapp callbacks can be handled elsewhere or dynamically
    "pay:",
    "admin:",
}

IGNORED_EXACT = {
    "noop",
}


def _read_py_files(*parts: str) -> list[Path]:
    base = ROOT.joinpath(*parts)
    return sorted(base.rglob("*.py"))


def _extract_string_literals_from_call(node: ast.Call) -> list[str]:
    values: list[str] = []
    for arg in list(node.args) + [kw.value for kw in node.keywords]:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            values.append(arg.value)
        elif isinstance(arg, ast.JoinedStr):
            # f"img_model:{model}" -> "img_model:"
            prefix = ""
            for part in arg.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    prefix += part.value
                else:
                    break
            if prefix:
                values.append(prefix)
    return values


def collect_keyboard_callbacks() -> set[str]:
    callbacks: set[str] = set()

    for path in _read_py_files("bot", "keyboards"):
        tree = ast.parse(path.read_text(encoding="utf-8"))

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

    for path in _read_py_files("bot", "handlers"):
        text = path.read_text(encoding="utf-8")

        # F.data == "..."
        for m in re.finditer(r'F\.data\s*==\s*["\']([^"\']+)["\']', text):
            patterns.add(m.group(1))

        # F.data.startswith("...")
        for m in re.finditer(r'F\.data\.startswith\(["\']([^"\']+)["\']\)', text):
            patterns.add(m.group(1))

    return patterns


def callback_is_covered(callback: str, patterns: set[str]) -> bool:
    if callback in IGNORED_EXACT:
        return True
    if any(callback.startswith(prefix) for prefix in IGNORED_PREFIXES):
        return True

    return any(callback == p or callback.startswith(p) for p in patterns)


def test_critical_callbacks_are_covered():
    patterns = collect_handler_patterns()
    missing = sorted(cb for cb in CRITICAL_CALLBACKS if not callback_is_covered(cb, patterns))
    assert not missing, "Missing handlers for critical callbacks:\n" + "\n".join(missing)


def test_keyboard_callbacks_have_handlers():
    callbacks = collect_keyboard_callbacks()
    patterns = collect_handler_patterns()

    # Only test bot-owned callback namespaces. This avoids false positives from payment/admin extras.
    owned_prefixes = (
        "menu:",
        "img",
        "vpar",
        "vid_",
        "music",
        "feed:",
        "prompts:",
        "balance",
    )

    relevant = {
        cb for cb in callbacks
        if cb.startswith(owned_prefixes)
    }

    missing = sorted(cb for cb in relevant if not callback_is_covered(cb, patterns))

    assert not missing, (
        "Keyboard callback_data without callback_query handler:\n"
        + "\n".join(missing)
        + "\n\nHandlers found:\n"
        + "\n".join(sorted(patterns))
    )


def test_no_missing_image_dynamic_handlers():
    patterns = collect_handler_patterns()

    required_prefixes = [
        "img_dyn:mode:",
        "img_dyn:ratio:",
        "img_dyn:quality:",
        "img_dyn:count:",
        "img_dyn:enhance:",
        "img_dyn:continue:",
        "img_scn:",
    ]

    missing = [p for p in required_prefixes if not any(h == p or h.startswith(p) or p.startswith(h) for h in patterns)]
    assert not missing, "Missing image dynamic handler prefixes: " + ", ".join(missing)


def test_no_duplicate_top_level_function_names_in_models():
    path = ROOT / "bot" / "keyboards" / "models.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    names: dict[str, int] = {}
    duplicates: list[str] = []

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            names[node.name] = names.get(node.name, 0) + 1
            if names[node.name] == 2:
                duplicates.append(node.name)

    assert not duplicates, "Duplicate functions in bot/keyboards/models.py: " + ", ".join(duplicates)
