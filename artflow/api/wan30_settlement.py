"""WAN3 post-completion billing for provider-derived edit/auto durations.

The quoted reserve is the maximum collectible amount. A verified, APIX-owned
MP4 determines actual output seconds; unused credits are returned in the same
transaction that marks the generation complete. No additional paid POST or
customer debit is allowed here.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from api.media_gateway import MediaKind, probe_local_media
from api.public_files import local_upload_path_from_url


@dataclass(frozen=True, slots=True)
class Wan30Settlement:
    output_seconds: float
    output_billable_seconds: int
    billable_seconds: int
    final_credits: float
    refund_credits: float
    overage_seconds: int


def _finite_float(value: object, field: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Invalid WAN billing {field}")
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"Invalid WAN billing {field}") from exc
    if not math.isfinite(number) or (number < 0 if allow_zero else number <= 0):
        raise ValueError(f"Invalid WAN billing {field}")
    return number


def calculate_wan30_settlement(
    billing: dict, *, output_seconds: float, credits_spent: float,
) -> Wan30Settlement:
    """Pure calculation based on server-stored quote and measured output.

    Charge the ceiling of precise verified input+output duration, exactly as
    the pre-charge Wan3 quote does. Do not round the output independently:
    the combined total is the billed quantity, not each component's ceiling.
    """
    output_seconds = _finite_float(output_seconds, "output_seconds")
    if output_seconds > 30.5:
        raise ValueError("WAN result exceeds maximum supported output duration")
    rate = _finite_float(billing.get("rate"), "rate")
    reserved_credits = _finite_float(billing.get("reserved_credits"), "reserve")
    reserved_seconds = _finite_float(billing.get("reserved_billable_seconds"), "reserved seconds")
    video_seconds = _finite_float(billing.get("input_video_seconds"), "input seconds", allow_zero=True)
    charged = _finite_float(credits_spent, "charged")
    if reserved_seconds != int(reserved_seconds) or reserved_seconds > 30:
        raise ValueError("Invalid WAN billing reserve seconds")
    if video_seconds > 15:
        raise ValueError("Invalid WAN billing input video duration")
    if not math.isclose(reserved_credits, rate * reserved_seconds, rel_tol=0, abs_tol=1e-4):
        raise ValueError("WAN quote rate/reserve mismatch")
    if not math.isclose(charged, reserved_credits, rel_tol=0, abs_tol=1e-4):
        raise ValueError("WAN charged amount/quote mismatch")
    if billing.get("settled") is not False:
        raise ValueError("WAN billing has already settled")

    output_units = max(1, math.ceil(output_seconds - 1e-9))
    billable = math.ceil(video_seconds + output_seconds - 1e-9)
    capped = min(billable, int(reserved_seconds))
    final_credits = round(capped * rate, 6)
    refund_credits = round(max(0, charged - final_credits), 6)
    return Wan30Settlement(
        output_seconds=round(output_seconds, 3),
        output_billable_seconds=output_units,
        billable_seconds=capped,
        final_credits=round(charged - refund_credits, 6),
        refund_credits=refund_credits,
        overage_seconds=max(0, billable - capped),
    )


async def probe_wan30_output_seconds(url: str) -> float:
    """Only trust a locally persisted MP4, never a remote-provider URL or UI claim."""
    file = local_upload_path_from_url(str(url))
    if not file or not file.is_file() or file.suffix.lower() != ".mp4":
        raise ValueError("WAN settlement requires an APIX-owned MP4")
    with file.open("rb") as stream:
        header = stream.read(12)
    if len(header) < 12 or header[4:8] != b"ftyp" or header[8:12] == b"qt  ":
        raise ValueError("WAN settlement requires verified MP4 content")
    info = await probe_local_media(file, MediaKind.VIDEO)
    if not info.width or not info.height:
        raise ValueError("WAN settlement requires a playable video stream")
    return _finite_float(info.duration_seconds, "measured output seconds")
