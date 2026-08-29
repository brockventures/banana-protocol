"""
banana.classifier - 3-Tier Address-Aware Message Ingestion Engine.
Determines whether an inbound channel message requires action, ambient classification, or silence.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List
from .envelope import parse_envelope, HandoffEnvelope

class Tier(Enum):
    DIRECT = "direct"          # Unconditional response required
    CLASSIFIED = "classified"  # Needs semantic relevance classifier
    SILENT = "silent"          # Passive buffering only; no reply

@dataclass
class Event:
    sender: str
    content: str
    is_bot: bool = False
    mentions: Optional[List[str]] = None
    is_reply_to_agent: bool = False
    envelope: Optional[HandoffEnvelope] = None

class IngestionClassifier:
    """Evaluates message targeting across Crab Cavern peer bots."""

    def __init__(self, agent_name: str, bot_id: Optional[str] = None):
        self.agent_name = agent_name.lower()
        self.bot_id = str(bot_id) if bot_id else ""

    def evaluate(self, event: Event) -> Tier:
        content = event.content.strip()
        env = event.envelope or parse_envelope(content)

        # 1. Handoff envelope rule: reply: "none" is unconditionally silent
        if env and not env.should_reply():
            return Tier.SILENT

        # 2. Handoff targeted specifically to this agent
        if env and env.is_addressed_to(self.agent_name):
            return Tier.DIRECT

        # 3. Direct Discord @-mention or reply
        if event.is_reply_to_agent:
            return Tier.DIRECT

        if self.bot_id and (f"<@{self.bot_id}>" in content or f"<@!{self.bot_id}>" in content):
            return Tier.DIRECT

        if event.mentions and self.bot_id and self.bot_id in event.mentions:
            return Tier.DIRECT

        # 4. Name invocation at start of prompt (e.g. "Zero:", "Hey zero,")
        name_pattern = rf"(?:^|[\s,;])(?:hey\s+)?@?{re.escape(self.agent_name)}(?:\b|[!?:,])"
        if re.search(name_pattern, content, re.IGNORECASE):
            return Tier.DIRECT

        # 5. Bot noise filter: Ignore peer bot chatter under 4 words without explicit targeting
        if event.is_bot:
            words = [w for w in content.split() if any(c.isalnum() for c in w)]
            if len(words) < 4:
                return Tier.SILENT

        # 6. Unaddressed broadcast discourse -> Candidate for semantic classifier or silent
        return Tier.CLASSIFIED
