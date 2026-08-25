from __future__ import annotations

from typing import Any


def _dedupe_urls(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        source = value if isinstance(value, (list, tuple, set)) else [value]
        for item in source:
            clean = str(item or "").strip()
            if clean and clean not in result:
                result.append(clean)
    return result


def _image_model_keys(routes: Any) -> set[str]:
    keys = {
        str(getattr(item, "value", item))
        for item in getattr(routes, "ImageModel", [])
    }
    keys.update(str(item) for item in getattr(routes, "_MJ_STUDIO_IMAGE_MODELS", set()))
    return keys


def _patch_router_endpoint(routes: Any, original: Any, replacement: Any) -> None:
    """Swap only the callable; preserve FastAPI's already-built body/dependency schema."""
    for route in getattr(routes.router, "routes", []):
        if getattr(route, "endpoint", None) is not original:
            continue
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            dependant.call = replacement


def install_feed_repeat_contract(routes: Any) -> None:
    """Keep feed source as the primary reference and remove duplicate user refs.

    The feed repeat UI sends the source separately from user-uploaded references.
    The legacy endpoint preferred user refs for image repeats and therefore could
    silently drop the source. It also accepted the same upload simultaneously as
    ``image_url`` and ``reference_urls[0]``, forwarding duplicates to providers.

    This wrapper normalizes the request before the existing endpoint executes:
    * image repeat: source first, then unique user references;
    * video repeat: source remains separate, user references are unique;
    * callers that omit ``source_image_url`` fall back to the public feed result.
    """
    if getattr(routes, "_feed_repeat_contract_installed", False):
        return

    original = routes.remix_feed_post
    image_keys = _image_model_keys(routes)

    async def remix_feed_post_with_reference_contract(
        gen_id: int,
        body,
        session=routes.Depends(routes.get_session),
        user=routes.Depends(routes.get_miniapp_user),
        surface: str = "miniapp",
    ):
        user_refs = _dedupe_urls(
            getattr(body, "image_url", None),
            getattr(body, "reference_urls", None),
        )

        if str(getattr(body, "model", "")) in image_keys:
            source_url = str(getattr(body, "source_image_url", None) or "").strip()
            if not source_url:
                source = await routes.repo.get_public_feed_generation(session, gen_id)
                if source is not None:
                    source_urls = routes._generation_result_urls(source)
                    source_url = source_urls[0] if source_urls else ""

            merged_refs = _dedupe_urls(source_url, user_refs)
            body = body.model_copy(
                update={
                    "source_image_url": source_url or None,
                    "image_url": merged_refs[0] if merged_refs else None,
                    "reference_urls": merged_refs[1:] if merged_refs else [],
                }
            )
        else:
            # Frontend transports the primary uploaded reference in image_url and
            # repeats it in reference_urls for compatibility. Keep only one copy.
            body = body.model_copy(
                update={
                    "image_url": user_refs[0] if user_refs else None,
                    "reference_urls": user_refs[1:] if user_refs else [],
                }
            )

        return await original(
            gen_id=gen_id,
            body=body,
            session=session,
            user=user,
            surface=surface,
        )

    # Keep this annotation for any later introspection, but do not make FastAPI
    # rebuild the route: its original dependant already knows this is JSON body.
    remix_feed_post_with_reference_contract.__annotations__["body"] = routes.FeedRemixRequest
    routes.remix_feed_post = remix_feed_post_with_reference_contract
    _patch_router_endpoint(routes, original, remix_feed_post_with_reference_contract)
    routes._feed_repeat_contract_installed = True
