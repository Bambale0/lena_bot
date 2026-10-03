"""Copyable provider task references for Telegram generation messages."""

from html import escape


def provider_task_reference(task_id: str | None, *, language: str = "ru") -> str:
    """Render the original provider ID without APIX transport namespaces."""
    raw = str(task_id or "").strip()
    if raw.startswith("web:"):
        raw = raw.removeprefix("web:")
    # Synchronous Comet images use this local sentinel without a provider ID.
    if raw == "comet:image:direct":
        return ""
    if raw.startswith(("neironych:", "nexus:")):
        raw = raw.split(":", 1)[1]
    elif raw.startswith("comet:"):
        parts = raw.split(":", 2)
        if len(parts) == 3 and parts[1]:
            raw = parts[2]
    if not raw:
        return ""
    label = "ID задачи" if language == "ru" else "Task ID"
    return f"\n\n🆔 {label}: <code>{escape(raw)}</code>"
