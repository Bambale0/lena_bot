from __future__ import annotations

import importlib


MODULES = [
    "main",
    "api.music_service",
    "api.image_service",
    "api.video_service",
    "api.miniapp_routes",
    "bot.keyboards.models",
    "bot.handlers.image_gen",
    "bot.handlers.video_gen",
    "bot.handlers.music_gen",
]


def test_core_modules_import():
    failed = []
    for module in MODULES:
        try:
            importlib.import_module(module)
        except Exception as exc:
            failed.append(f"{module}: {type(exc).__name__}: {exc}")

    assert not failed, "Import failures:\n" + "\n".join(failed)
