"""Provider adapters transform external protocols into neutral payment results.

Deep Link commands may contain credentials and must never be logged or persisted.
"""

from .cielo import CieloSmartAdapter
from .registry import get_adapter, registered_adapters

__all__ = ('CieloSmartAdapter', 'get_adapter', 'registered_adapters')
