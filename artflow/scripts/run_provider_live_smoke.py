#!/usr/bin/env python3
"""Run provider contracts through the authenticated APIX public gateway.

This command spends provider credits. By default it only validates the manifest;
pass --execute and explicit contract IDs (or --all) to make network requests.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.provider_contract_catalog import ALL_CONTRACTS
from api.provider_operation_registry import OPERATION_SPECS
from api.provider_smoke_manifest import SMOKE_CASES

_PLACEHOLDER = re.compile(r"^\$\{([A-Z0-9_]+)\}$")


def validate_manifest() -> list[str]:
    errors: list[str] = []
    catalog_ids = {contract.contract_id for contract in ALL_CONTRACTS}
    case_ids = set(SMOKE_CASES)
    if missing := sorted(catalog_ids - case_ids):
        errors.append(f"missing smoke cases: {missing}")
    if unknown := sorted(case_ids - catalog_ids):
        errors.append(f"unknown smoke cases: {unknown}")
    for contract_id, case in SMOKE_CASES.items():
        if case.contract_id != contract_id:
            errors.append(f"{contract_id}: case.contract_id mismatch")
        if contract_id not in OPERATION_SPECS:
            errors.append(f"{contract_id}: no operation executor")
        if not isinstance(case.params, dict):
            errors.append(f"{contract_id}: params must be an object")
    return errors


def _substitute(value: Any) -> Any:
    if isinstance(value, str):
        match = _PLACEHOLDER.fullmatch(value)
        if not match:
            return value
        name = match.group(1)
        env_value = os.getenv(name)
        if env_value is None:
            raise RuntimeError(f"Missing required smoke environment variable: {name}")
        return env_value
    if isinstance(value, list):
        return [_substitute(item) for item in value]
    if isinstance(value, dict):
        return {key: _substitute(item) for key, item in value.items()}
    return value


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    bearer = os.getenv("APIX_SMOKE_BEARER_TOKEN", "").strip()
    init_data = os.getenv("APIX_SMOKE_TELEGRAM_INIT_DATA", "").strip()
    session_token = os.getenv("APIX_SMOKE_SESSION_TOKEN", "").strip()
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    if init_data:
        headers["X-Telegram-Init-Data"] = init_data
    if session_token:
        headers["X-APIX-Session"] = session_token
    if len(headers) == 1:
        raise RuntimeError(
            "Configure APIX_SMOKE_BEARER_TOKEN, APIX_SMOKE_TELEGRAM_INIT_DATA "
            "or APIX_SMOKE_SESSION_TOKEN"
        )
    return headers


def _run_case(
    client: httpx.Client,
    base_url: str,
    contract_id: str,
    *,
    poll_interval: float,
) -> dict[str, Any]:
    case = SMOKE_CASES[contract_id]
    params = _substitute(case.params)
    response = client.post(
        f"{base_url}/api/v1/provider-operations/{contract_id}",
        json={"params": params},
    )
    response.raise_for_status()
    accepted = response.json()
    generation_id = accepted.get("generation_id")
    if accepted.get("status") in {"completed", "failed", "cancelled"} or not generation_id:
        return accepted

    deadline = time.monotonic() + case.terminal_timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        status_response = client.get(
            f"{base_url}/api/v1/provider-operations/generations/{generation_id}"
        )
        status_response.raise_for_status()
        payload = status_response.json()
        if payload.get("status") in {"completed", "failed", "cancelled"}:
            return payload
    raise TimeoutError(f"{contract_id} did not finish within {case.terminal_timeout_seconds}s")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contracts", nargs="*", help="Contract IDs to execute")
    parser.add_argument("--all", action="store_true", help="Execute all contracts (spends credits)")
    parser.add_argument("--execute", action="store_true", help="Actually call providers")
    parser.add_argument("--base-url", default=os.getenv("APIX_SMOKE_BASE_URL", "https://apixbotai.com"))
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    errors = validate_manifest()
    if errors:
        print("Provider smoke manifest failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Provider smoke manifest OK: {len(SMOKE_CASES)} contracts")
    if not args.execute:
        print("Dry validation only. Pass --execute with contract IDs or --all to spend credits.")
        return 0

    selected = sorted(SMOKE_CASES) if args.all else args.contracts
    if not selected:
        print("Refusing to spend credits without explicit contract IDs or --all")
        return 2
    unknown = sorted(set(selected) - set(SMOKE_CASES))
    if unknown:
        print(f"Unknown contract IDs: {unknown}")
        return 2

    results: dict[str, Any] = {}
    failures = 0
    with httpx.Client(headers=_headers(), timeout=90.0, follow_redirects=True) as client:
        for contract_id in selected:
            print(f"Running {contract_id} ...", flush=True)
            try:
                result = _run_case(
                    client,
                    args.base_url.rstrip("/"),
                    contract_id,
                    poll_interval=args.poll_interval,
                )
                results[contract_id] = result
                if result.get("status") != "completed":
                    failures += 1
                    print(f"FAILED {contract_id}: {result}")
                else:
                    print(f"OK {contract_id}")
            except Exception as exc:
                failures += 1
                results[contract_id] = {"error": str(exc)}
                print(f"ERROR {contract_id}: {exc}")

    rendered = json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
