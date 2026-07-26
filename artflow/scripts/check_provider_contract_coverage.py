#!/usr/bin/env python3
"""Validate and render the APIX provider-contract coverage dashboard."""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.image_service import ImageModel  # noqa: E402
from api.kie_model_specs import IMAGE_SPECS, VIDEO_SPECS  # noqa: E402
from api.provider_contract_catalog import ALL_CONTRACTS, ProviderContract  # noqa: E402
from api.video_service import VideoModel  # noqa: E402

DEFAULT_DASHBOARD = ROOT / "docs" / "provider_contract_coverage.md"
DEFAULT_JSON = ROOT / "docs" / "provider_contract_coverage.json"


def _duplicates(values: Iterable[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def _entrypoint_exists(entrypoint: str) -> bool:
    module_name, separator, attribute_path = entrypoint.partition(":")
    if not separator or not module_name or not attribute_path:
        return False
    try:
        value = importlib.import_module(module_name)
        for part in attribute_path.split("."):
            value = getattr(value, part)
    except (ImportError, AttributeError):
        return False
    return callable(value)


def _file_exists(path: str) -> bool:
    candidate = ROOT / path
    return candidate.exists() and candidate.is_file()


def _official_url(value: str) -> bool:
    return value.startswith("https://") and " " not in value


def validate_contracts(*, strict_product: bool = False) -> list[str]:
    errors: list[str] = []
    contract_ids = [contract.contract_id for contract in ALL_CONTRACTS]
    duplicate_ids = _duplicates(contract_ids)
    if duplicate_ids:
        errors.append(f"duplicate contract_id values: {duplicate_ids}")

    image_models = {model.value for model in ImageModel}
    catalog_image_models = {
        contract.model for contract in ALL_CONTRACTS if contract.contract_id.startswith("image.")
    }
    missing_images = sorted(image_models - catalog_image_models)
    if missing_images:
        errors.append(f"ImageModel values missing from catalog: {missing_images}")

    video_models = {model.value for model in VideoModel}
    catalog_video_models = {
        contract.model
        for contract in ALL_CONTRACTS
        if contract.contract_id.startswith("video.")
    }
    missing_videos = sorted(video_models - catalog_video_models)
    if missing_videos:
        errors.append(f"VideoModel values missing from catalog: {missing_videos}")

    runtime_kie_models = set(IMAGE_SPECS) | set(VIDEO_SPECS)
    missing_runtime = sorted(runtime_kie_models - {contract.model for contract in ALL_CONTRACTS})
    if missing_runtime:
        errors.append(f"KIE runtime specs missing from catalog: {missing_runtime}")

    smoke_ids = [contract.live_smoke_id for contract in ALL_CONTRACTS if contract.live_smoke_id]
    duplicate_smoke_ids = _duplicates(smoke_ids)
    if duplicate_smoke_ids:
        errors.append(f"duplicate live_smoke_id values: {duplicate_smoke_ids}")

    for contract in ALL_CONTRACTS:
        prefix = contract.contract_id
        if not contract.contract_valid:
            errors.append(f"{prefix}: incomplete base contract metadata")
        if not all(_official_url(url) for url in contract.official_docs):
            errors.append(f"{prefix}: official_docs must contain HTTPS URLs")
        if not all(_entrypoint_exists(item) for item in contract.backend_entrypoints):
            bad = [item for item in contract.backend_entrypoints if not _entrypoint_exists(item)]
            errors.append(f"{prefix}: missing backend entrypoints: {bad}")
        if not all(_file_exists(item) for item in contract.contract_tests):
            bad = [item for item in contract.contract_tests if not _file_exists(item)]
            errors.append(f"{prefix}: missing contract test files: {bad}")
        if strict_product:
            if not contract.has_user_surface:
                errors.append(f"{prefix}: no Telegram, Mini App or public API surface")
            if not contract.live_smoke_id:
                errors.append(f"{prefix}: no live smoke scenario")

    return errors


def _status(value: bool) -> str:
    return "✅" if value else "❌"


def _contract_row(contract: ProviderContract) -> str:
    surfaces = ", ".join(
        name
        for name, enabled in (
            ("TG", contract.telegram),
            ("Mini App", contract.miniapp),
            ("API", contract.public_api),
        )
        if enabled
    ) or "—"
    contract_ready = contract.contract_valid
    product_ready = contract_ready and contract.has_user_surface and bool(contract.live_smoke_id)
    return (
        f"| `{contract.contract_id}` | `{contract.model}` | {', '.join(contract.modes)} | "
        f"{surfaces} | {_status(contract_ready)} | {_status(bool(contract.live_smoke_id))} | "
        f"{_status(product_ready)} |"
    )


def render_markdown() -> str:
    total = len(ALL_CONTRACTS)
    contract_ready = sum(1 for item in ALL_CONTRACTS if item.contract_valid)
    surfaced = sum(1 for item in ALL_CONTRACTS if item.has_user_surface)
    smoke_declared = sum(1 for item in ALL_CONTRACTS if item.live_smoke_id)
    product_ready = sum(
        1
        for item in ALL_CONTRACTS
        if item.contract_valid and item.has_user_surface and item.live_smoke_id
    )
    lines = [
        "# APIX provider contract coverage",
        "",
        "> Generated by `scripts/check_provider_contract_coverage.py`. Do not edit manually.",
        "",
        f"- Contracts: **{total}**",
        f"- Contract-valid: **{contract_ready}/{total}**",
        f"- User-surfaced: **{surfaced}/{total}**",
        f"- Live-smoke declared: **{smoke_declared}/{total}**",
        f"- Product-ready: **{product_ready}/{total}**",
        "",
        "| Contract | Provider model / operation | Modes | User surfaces | Contract | Smoke | Product |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    lines.extend(_contract_row(contract) for contract in ALL_CONTRACTS)
    lines.extend(
        [
            "",
            "## Definitions",
            "",
            "- **Contract-valid**: official docs, dated revision, callable backend entrypoint and contract-test files exist.",
            "- **User-surfaced**: available through Telegram, Mini App or the public API.",
            "- **Smoke**: a unique live-smoke scenario ID is declared.",
            "- **Product-ready**: all three conditions are true.",
            "",
        ]
    )
    return "\n".join(lines)


def render_json() -> str:
    payload = {
        "contracts": [
            {
                **asdict(contract),
                "contract_valid": contract.contract_valid,
                "has_user_surface": contract.has_user_surface,
                "product_ready": bool(
                    contract.contract_valid
                    and contract.has_user_surface
                    and contract.live_smoke_id
                ),
            }
            for contract in ALL_CONTRACTS
        ]
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _check_generated(path: Path, expected: str) -> bool:
    return path.exists() and path.read_text(encoding="utf-8") == expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Validate metadata and generated files")
    parser.add_argument("--strict-product", action="store_true", help="Require a user surface and smoke ID")
    parser.add_argument("--write", action="store_true", help="Write Markdown and JSON dashboards")
    parser.add_argument("--dashboard", type=Path, default=DEFAULT_DASHBOARD)
    parser.add_argument("--json", dest="json_path", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    errors = validate_contracts(strict_product=args.strict_product)
    markdown = render_markdown()
    json_text = render_json()

    if args.write:
        args.dashboard.parent.mkdir(parents=True, exist_ok=True)
        args.dashboard.write_text(markdown, encoding="utf-8")
        args.json_path.write_text(json_text, encoding="utf-8")

    if args.check:
        if not _check_generated(args.dashboard, markdown):
            errors.append(f"generated dashboard is stale: {args.dashboard}")
        if not _check_generated(args.json_path, json_text):
            errors.append(f"generated JSON is stale: {args.json_path}")

    if errors:
        print("Provider contract coverage failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Provider contract coverage OK: {len(ALL_CONTRACTS)} contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
