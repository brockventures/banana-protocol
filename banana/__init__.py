"""
banana - Canonical Multi-Agent Coordination Protocol for Crab Cavern.
Provides turn-claim locking (Banana mutex), v0 handoff envelope parsing, and address-aware message routing.
"""

from .client import BananaClient, AsyncBananaClient, BananaError, BananaBlockedError, BananaRoundLimitExceededError
from .envelope import parse_envelope, format_envelope, HandoffEnvelope
from .classifier import IngestionClassifier, Tier, Event

__version__ = "0.2.0"
__all__ = [
    "BananaClient",
    "AsyncBananaClient",
    "BananaError",
    "BananaBlockedError",
    "BananaRoundLimitExceededError",
    "parse_envelope",
    "format_envelope",
    "HandoffEnvelope",
    "IngestionClassifier",
    "Tier",
    "Event"
]
