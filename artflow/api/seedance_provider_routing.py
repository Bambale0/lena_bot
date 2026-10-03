"""Provider order for Seedance product routes."""

import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from core.config import settings

logger = logging.getLogger(__name__)
Result = TypeVar("Result")


async def submit_seedance(
    product_model: str,
    *,
    kie: Callable[[], Awaitable[Result]],
    neironych: Callable[[], Awaitable[Result]],
) -> Result:
    """Try the configured primary once, then the same model's secondary."""
    primary = settings.SEEDANCE_PRIMARY_PROVIDER
    secondary = "neironych" if primary == "kieai" else "kieai"
    providers = {"kieai": kie, "neironych": neironych}
    try:
        return await providers[primary]()
    except Exception as primary_exc:
        logger.warning(
            "%s %s submission failed; falling back to %s: %s",
            product_model, primary, secondary, primary_exc,
        )
        try:
            return await providers[secondary]()
        except Exception as fallback_exc:
            raise RuntimeError(
                f"{product_model} failed via primary {primary} and {secondary} fallback: "
                f"primary={primary_exc}; fallback={fallback_exc}"
            ) from fallback_exc
