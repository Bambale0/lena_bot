"""API package bootstrap.

Provider contract overrides are applied before service modules import the shared
model registries. This keeps payload builders, UI capabilities and tests on one
current contract while legacy definitions are migrated incrementally.
"""
from __future__ import annotations

import importlib.abc
import importlib.util
import sys
from types import ModuleType
from typing import Any

from api.provider_spec_overrides import apply_provider_spec_overrides
from api.prompt_privacy import install_miniapp_prompt_privacy

apply_provider_spec_overrides()

# Keep legacy APIX Grok keys compatible with saved sessions while routing all
# new requests through the current KIE Grok Imagine Video 1.5 Preview contract.
from api import image_service as _image_service
from api import kieai_client as _kieai_client
from api.feed_repeat_contract import install_feed_repeat_contract
from api.grok15_adapter import install_grok15_adapter
from api.minimax_h3_adapter import (
    install_minimax_h3_keyboard_support,
    install_minimax_h3_miniapp,
    install_minimax_h3_provider_support,
)
from api.minimax_h3_pricing import install_minimax_h3_seed_rows
from api.minimax_h3_product_surface import install_minimax_h3_product_surface
from api.minimax_h3_runtime_guards import install_minimax_h3_runtime_guards
from api.pinterest_contract import (
    install_pinterest_miniapp_contract,
    install_pinterest_provider_contract,
)
from api.repeat_runtime import install_repeat_runtime
from api.seedance25_adapter import (
    install_seedance25_keyboard_support,
    install_seedance25_miniapp,
    install_seedance25_provider_support,
)
from api.seedance25_pricing import install_seedance25_seed_rows
from api.seedance25_product_surface import install_seedance25_product_surface
from api.suno_source_audio_routes import install_suno_source_audio_routes
from api.video_runtime_fixes import install_video_runtime_fixes
from api.video_ui_capability_guards import strip_seedance25_omni_id_controls
from bot.keyboards import models as _repeat_keyboards
from bot.services.safe_repeat_ui import install_safe_repeat_keyboard_support
from db import repository as _repeat_repository

install_grok15_adapter(_kieai_client)
install_seedance25_seed_rows()
install_seedance25_provider_support()
install_seedance25_keyboard_support()
install_seedance25_product_surface()
install_minimax_h3_seed_rows()
install_minimax_h3_provider_support()
install_minimax_h3_runtime_guards()
install_minimax_h3_keyboard_support()
install_minimax_h3_product_surface()
install_video_runtime_fixes()
strip_seedance25_omni_id_controls()
install_repeat_runtime(_repeat_repository)
install_safe_repeat_keyboard_support(_repeat_keyboards)
install_pinterest_provider_contract(_image_service)


class _MiniappLabelLoader(importlib.abc.Loader):
    """Delegate normal import, then install shared Mini App presentation hooks."""

    def __init__(self, wrapped: importlib.abc.Loader, finder: "_MiniappLabelFinder") -> None:
        self.wrapped = wrapped
        self.finder = finder

    def create_module(self, spec: Any) -> ModuleType | None:
        create = getattr(self.wrapped, "create_module", None)
        return create(spec) if create else None

    def exec_module(self, module: ModuleType) -> None:
        self.wrapped.exec_module(module)
        from api.admin_model_visibility import install_admin_model_visibility
        from api.feed_media_viewer import install_feed_media_viewer
        from api.kling_motion_visibility import install_kling_motion_visibility
        from api.video_request_compat import install_video_request_compat
        from bot.ui.model_labels import install_miniapp_model_labels, install_repository_model_labels
        from db import repository
        from db.feed_relevance import install_feed_relevance

        install_kling_motion_visibility(repository)
        install_miniapp_model_labels(module)
        install_repository_model_labels(repository)
        install_feed_relevance(repository)
        install_feed_media_viewer(module)
        install_feed_repeat_contract(module)
        install_miniapp_prompt_privacy(module)
        install_pinterest_miniapp_contract(module)
        install_video_request_compat(module)
        install_seedance25_miniapp(module)
        install_minimax_h3_miniapp(module)
        install_minimax_h3_product_surface(module)
        install_video_runtime_fixes(module)
        install_suno_source_audio_routes(module)
        strip_seedance25_omni_id_controls(module)
        install_admin_model_visibility(module)
        if self.finder in sys.meta_path:
            sys.meta_path.remove(self.finder)


class _MiniappLabelFinder(importlib.abc.MetaPathFinder):
    target = "api.miniapp_routes"

    def find_spec(self, fullname: str, path: Any, target: ModuleType | None = None):
        if fullname != self.target:
            return None
        try:
            sys.meta_path.remove(self)
            spec = importlib.util.find_spec(fullname)
        finally:
            sys.meta_path.insert(0, self)
        if spec is None or spec.loader is None:
            return spec
        spec.loader = _MiniappLabelLoader(spec.loader, self)
        return spec


if "api.miniapp_routes" not in sys.modules:
    _miniapp_label_finder = _MiniappLabelFinder()
    sys.meta_path.insert(0, _miniapp_label_finder)
else:
    from api.admin_model_visibility import install_admin_model_visibility
    from api.feed_media_viewer import install_feed_media_viewer
    from api.kling_motion_visibility import install_kling_motion_visibility
    from api.video_request_compat import install_video_request_compat
    from bot.ui.model_labels import install_miniapp_model_labels, install_repository_model_labels
    from db import repository
    from db.feed_relevance import install_feed_relevance

    miniapp_routes = sys.modules["api.miniapp_routes"]
    install_kling_motion_visibility(repository)
    install_miniapp_model_labels(miniapp_routes)
    install_repository_model_labels(repository)
    install_feed_relevance(repository)
    install_feed_media_viewer(miniapp_routes)
    install_feed_repeat_contract(miniapp_routes)
    install_miniapp_prompt_privacy(miniapp_routes)
    install_pinterest_miniapp_contract(miniapp_routes)
    install_video_request_compat(miniapp_routes)
    install_seedance25_miniapp(miniapp_routes)
    install_minimax_h3_miniapp(miniapp_routes)
    install_minimax_h3_product_surface(miniapp_routes)
    install_video_runtime_fixes(miniapp_routes)
    install_suno_source_audio_routes(miniapp_routes)
    strip_seedance25_omni_id_controls(miniapp_routes)
    install_admin_model_visibility(miniapp_routes)
