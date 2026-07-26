from __future__ import annotations

from api.image_service import ImageModel
from api.provider_contract_catalog import ALL_CONTRACTS
from api.video_service import VideoModel
from scripts.check_provider_contract_coverage import validate_contracts


def test_provider_contract_inventory_is_structurally_complete() -> None:
    assert validate_contracts(strict_product=False) == []


def test_every_runtime_image_model_is_catalogued() -> None:
    catalog_models = {
        contract.model
        for contract in ALL_CONTRACTS
        if contract.contract_id.startswith("image.")
    }
    assert {model.value for model in ImageModel} <= catalog_models


def test_every_runtime_video_model_is_catalogued() -> None:
    catalog_models = {
        contract.model
        for contract in ALL_CONTRACTS
        if contract.contract_id.startswith("video.")
    }
    assert {model.value for model in VideoModel} <= catalog_models


def test_contract_and_smoke_ids_are_unique() -> None:
    contract_ids = [contract.contract_id for contract in ALL_CONTRACTS]
    smoke_ids = [contract.live_smoke_id for contract in ALL_CONTRACTS if contract.live_smoke_id]
    assert len(contract_ids) == len(set(contract_ids))
    assert len(smoke_ids) == len(set(smoke_ids))


def test_every_contract_records_official_docs_revision() -> None:
    for contract in ALL_CONTRACTS:
        assert contract.docs_verified_on == "2026-07-26"
        assert contract.official_docs
        assert all(url.startswith("https://") for url in contract.official_docs)
