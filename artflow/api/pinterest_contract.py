"""Compatibility shim for historical Pinterest repeat imports.

Pinterest is a standalone Service. New runtime code lives in
``api.pinterest_service_contract`` and does not depend on Trends/UserPrompt.
This module only preserves the old context-manager import used by historical
repeat handlers while those generations remain repeatable.
"""

from api.pinterest_service_contract import (
    pinterest_service_provider_context as pinterest_provider_context,
)

__all__ = ["pinterest_provider_context"]
