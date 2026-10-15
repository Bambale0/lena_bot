from api import provider_operation_bindings  # noqa: F401
from api import provider_operation_registry as registry
from api.provider_contract_catalog import ALL_CONTRACTS


def test_catalog_public_exposure_matches_registered_public_operations():
    assert {c.contract_id for c in ALL_CONTRACTS if c.public_api} == set(registry.PUBLIC_API_CONTRACT_IDS)
    assert all(c.has_user_surface for c in ALL_CONTRACTS if c.contract_id in registry.PUBLIC_API_CONTRACT_IDS)


def test_nonbillable_public_read_operations_can_be_structurally_ready():
    reads = [c for c in ALL_CONTRACTS if c.contract_id in {"midjourney.fetch", "midjourney.list"}]
    assert reads and all(c.product_ready for c in reads)


def test_generated_json_and_markdown_use_the_same_readiness():
    import json

    from scripts.check_provider_contract_coverage import render_json, render_markdown

    rows = json.loads(render_json())["contracts"]
    assert {row["contract_id"] for row in rows if row["public_api"]} == set(registry.PUBLIC_API_CONTRACT_IDS)
    assert all(row["product_ready"] for row in rows)
    total = len(rows)
    assert f"Product-ready: **{total}/{total}**" in render_markdown()
