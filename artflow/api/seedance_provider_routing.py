"""Provider order for Seedance product routes."""

import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from api.kieai_client import KieDefiniteRejection, KieSubmissionOutcomeUnknown
from api.neironych_seedance import NeironychPreSubmitFailure, NeironychSubmissionUnknown
from core.config import settings

logger = logging.getLogger(__name__)
Result = TypeVar("Result")


async def submit_seedance(
    product_model: str,
    *,
    kie: Callable[[], Awaitable[Result]],
    neironych: Callable[[], Awaitable[Result]],
) -> Result:
    """Route each paid request independently, never via another task's circuit.

    Unknown submissions and pre-POST durability failures never retry/fallback.
    A confirmed ordinary provider error may use the separately priced fallback.
    """
    primary = settings.SEEDANCE_PRIMARY_PROVIDER
    secondary = "neironych" if primary == "kieai" else "kieai"
    providers = {"kieai": kie, "neironych": neironych}
    try:
        return await providers[primary]()
    except (NeironychSubmissionUnknown, NeironychPreSubmitFailure,
            KieSubmissionOutcomeUnknown):
        raise
    except Exception as primary_exc:
        if primary == "kieai" and not isinstance(primary_exc, KieDefiniteRejection):
            # A generic Kie failure may hide an accepted POST with a lost reply.
            logger.warning(
                "Seedance Kie submission unclassified; no second paid POST model=%s",
                product_model,
            )
            raise
        logger.warning(
            "%s %s submission failed; falling back to %s: %s",
            product_model, primary, secondary, primary_exc,
        )
        try:
            return await providers[secondary]()
        except (NeironychSubmissionUnknown, NeironychPreSubmitFailure,
                KieSubmissionOutcomeUnknown):
            raise
        except Exception as fallback_exc:
            raise RuntimeError(
                f"{product_model} failed via primary {primary} and {secondary} fallback: "
                f"primary={primary_exc}; fallback={fallback_exc}"
            ) from fallback_exc
