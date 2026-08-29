"""
banana - Canonical Multi-Agent Coordination Protocol for Crab Cavern.
Provides turn-claim locking (Banana mutex), v0 handoff envelope parsing, and address-aware message routing.
"""

from .client import BananaClient, BananaError, BananaBlockedError
from .envelope import parse_envelope, format_envelope, HandoffEnvelope
from .classifier import IngestionClassifier, Tier, Event

__version__ = "0.1.0"
__all__ = [
    "BananaClient",
    "BananaError",
    "BananaBlockedError",
    "parse_envelope",
    "format_envelope",
    "HandoffEnvelope",
    "IngestionClassifier",
    "Tier",
    "Event"
]
