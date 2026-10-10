"""Read-only availability for ordinary public Mini App uploads.

No DNS/HTTP, ownership inference, signed-link renewal or global resolver change.
"""
from __future__ import annotations

import ipaddress
import re
import stat
from typing import Literal
from urllib.parse import unquote, urlparse

from api import public_files

ReferenceAvailability = Literal["available", "missing", "unknown", "forbidden", "temporary_error"]
_UPLOAD_IMAGE_NAME = re.compile(r"[0-9a-f]{32}(?:-[0-9a-f]{16})?\.(?:jpg|jpeg|png|webp)")


def inspect_local_photo_reference(url: str) -> ReferenceAvailability:
    """Return only a state. A known public URL is not proof of asset ownership."""
    if not url or url != url.strip() or any(ord(c) < 32 for c in url) or "\\" in url:
        return "forbidden"
    try:
        parsed = urlparse(url)
        if parsed.scheme:
            if parsed.scheme not in {"https", "http"} or not parsed.hostname or not parsed.netloc:
                return "forbidden"
            if parsed.username is not None or parsed.password is not None:
                return "forbidden"
            _ = parsed.port  # invalid/non-numeric ports must fail closed
            host = parsed.hostname.lower()
            if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
                return "forbidden"
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                if host.isdecimal() or host.startswith("0x"):
                    return "forbidden"
            else:
                if not address.is_global:
                    return "forbidden"
        elif not url.startswith("/") or url.startswith("//") or parsed.netloc:
            return "forbidden"
        decoded = unquote(parsed.path)
        if "\\" in decoded or any(ord(c) < 32 for c in decoded) or "%" in decoded:
            return "forbidden"
        if any(part in {".", ".."} for part in decoded.split("/")):
            return "forbidden"
        # We cannot validate a signature/query by looking at a local file.
        if parsed.query or parsed.fragment or parsed.params:
            return "unknown"
        path = public_files.local_upload_path_from_url(url)
        if path is None:
            return "unknown"
        relative = path.relative_to(public_files.UPLOAD_ROOT)
        # Match the existing upload route's namespace/filename contract, not
        # arbitrary files under a public mount (or server-side diagnostics).
        if len(relative.parts) != 2 or relative.parts[0] != "miniapp" or not _UPLOAD_IMAGE_NAME.fullmatch(relative.name):
            return "unknown"
        root = public_files.UPLOAD_ROOT.resolve()
        if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(root):
            return "forbidden"
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            return "forbidden"
        return "available" if info.st_size > 0 else "missing"
    except FileNotFoundError:
        return "missing"
    except (OSError, PermissionError):
        return "temporary_error"
    except (ValueError, RuntimeError):
        return "forbidden"
