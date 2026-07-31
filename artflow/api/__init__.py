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

apply_provider_spec_overrides()

# Keep legacy APIX Grok keys compatible with saved sessions while routing all
# new requests through the current KIE Grok Imagine Video 1.5 Preview contract.
from api import kieai_client as _kieai_client
from api.grok15_adapter import install_grok15_adapter

install_grok15_adapter(_kieai_client)


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
        from bot.ui.model_labels import install_miniapp_model_labels, install_repository_model_labels
        from db import repository
        from db.feed_relevance import install_feed_relevance

        install_miniapp_model_labels(module)
        install_repository_model_labels(repository)
        install_feed_relevance(repository)
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
    from bot.ui.model_labels import install_miniapp_model_labels, install_repository_model_labels
    from db import repository
    from db.feed_relevance import install_feed_relevance

    install_miniapp_model_labels(sys.modules["api.miniapp_routes"])
    install_repository_model_labels(repository)
    install_feed_relevance(repository)
