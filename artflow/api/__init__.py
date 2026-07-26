"""API package bootstrap.

Provider contract overrides are applied before service modules import the shared
model registries. This keeps payload builders, UI capabilities and tests on one
current contract while legacy definitions are migrated incrementally.
"""
from api.provider_spec_overrides import apply_provider_spec_overrides

apply_provider_spec_overrides()
