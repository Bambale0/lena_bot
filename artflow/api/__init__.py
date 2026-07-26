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
