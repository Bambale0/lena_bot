"""Provider order for Seedance product routes."""

import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from api.neironych_seedance import NeironychPreSubmitFailure, NeironychSubmissionUnknown
from core.config import settings
from core.seedance_reconciliation import neironych_route_paused

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
    if primary == "neironych" and await neironych_route_paused(product_model):
        # No Neironych request has been sent yet. A new KIE request is safe,
        # unlike replaying a previously accepted-but-unconfirmed paid job.
        logger.warning("Seedance new request routed to KIE: model=%s Neironych circuit open", product_model)
        return await kie()
    try:
        return await providers[primary]()
    except (NeironychSubmissionUnknown, NeironychPreSubmitFailure):
        raise
    except Exception as primary_exc:
        if secondary == "neironych" and await neironych_route_paused(product_model):
            logger.warning("Seedance fallback blocked by uncertain-submission circuit model=%s", product_model)
            raise
        logger.warning(
            "%s %s submission failed; falling back to %s: %s",
            product_model, primary, secondary, primary_exc,
        )
        try:
            return await providers[secondary]()
        except (NeironychSubmissionUnknown, NeironychPreSubmitFailure):
            raise
        except Exception as fallback_exc:
            raise RuntimeError(
                f"{product_model} failed via primary {primary} and {secondary} fallback: "
                f"primary={primary_exc}; fallback={fallback_exc}"
            ) from fallback_exc
