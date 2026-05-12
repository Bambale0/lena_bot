from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StartPayload:
    raw: str = ""
    ref_code: str | None = None
    target_kind: str | None = None
    target_id: int | None = None


_TARGET_PREFIXES = ("feed_", "prompt_")


def parse_start_payload(raw: str | None) -> StartPayload:
    payload = (raw or "").strip()
    if not payload:
        return StartPayload(raw="")

    ref_code: str | None = None
    target_kind: str | None = None
    target_id: int | None = None

    parts = [part.strip() for part in payload.split("__") if part.strip()]
    if not parts:
        parts = [payload]

    for part in parts:
        if part.startswith("ref_") and len(part) > 4:
            ref_code = part[4:]
            continue

        if part.startswith("feed_"):
            gen_id_raw = part.split("_", 1)[1]
            if gen_id_raw.isdigit():
                target_kind = "feed"
                target_id = int(gen_id_raw)
                continue

        if part.startswith("prompt_"):
            prompt_id_raw = part.split("_", 1)[1]
            if prompt_id_raw.isdigit():
                target_kind = "prompt"
                target_id = int(prompt_id_raw)
                continue

        if ref_code is None:
            ref_code = part

    if ref_code and ref_code.startswith(_TARGET_PREFIXES) and target_kind is not None:
        ref_code = None

    return StartPayload(raw=payload, ref_code=ref_code, target_kind=target_kind, target_id=target_id)


def build_start_payload(*, ref_code: str | None = None, target_kind: str | None = None, target_id: int | None = None) -> str:
    if ref_code and not target_kind:
        return ref_code

    parts: list[str] = []
    if ref_code:
        parts.append(f"ref_{ref_code}")
    if target_kind and target_id is not None:
        parts.append(f"{target_kind}_{int(target_id)}")
    return "__".join(parts) if parts else ""
