"""API package bootstrap.

Provider contract overrides are applied before service modules import the shared
model registries. This keeps payload builders, UI capabilities and tests on one
current contract while legacy definitions are migrated incrementally.
"""
from api.provider_spec_overrides import apply_provider_spec_overrides

apply_provider_spec_overrides()

# Keep legacy APIX Grok keys compatible with saved sessions while routing all
# new requests through the current KIE Grok Imagine Video 1.5 Preview contract.
from api import kieai_client as _kieai_client
from api.grok15_adapter import install_grok15_adapter

install_grok15_adapter(_kieai_client)

# Mini App historically had a separate naming dictionary. Import it once during
# package bootstrap and replace that presentation layer with the same catalog
# used by Telegram. Provider keys and pricing rows remain unchanged.
from api import miniapp_routes as _miniapp_routes
from bot.ui.model_labels import install_miniapp_model_labels

install_miniapp_model_labels(_miniapp_routes)
