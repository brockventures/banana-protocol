"""
banana.envelope - v0 Agent Handoff Envelope Parser & Serializer.
Standardized JSON envelope for cross-agent coordination in Crab Cavern.
"""

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

@dataclass
class EvidenceItem:
    src: str
    note: str

@dataclass
class ContextBox:
    holder: Optional[str] = None
    claimed_at: Optional[float] = None
    last_active_ts: Optional[float] = None
    released: bool = False
    state: Optional[str] = None
    blocked_on: Optional[str] = None
    waiting_on: Optional[str] = None

@dataclass
class HandoffEnvelope:
    v: int = 0
    kind: str = "answer"              # "question" | "answer" | "status" | "proposal" | "correction" | "finding" | "handoff"
    reply: str = "optional"           # "required" | "optional" | "none"
    subject: str = ""
    evidence: List[Dict[str, str]] = field(default_factory=list)
    supersedes: Optional[str] = None
    context_box: Optional[Dict[str, Any]] = None
    to: Optional[str] = None
    target: Optional[str] = None

    def should_reply(self) -> bool:
        """Returns False if reply is explicitly 'none'."""
        return self.reply.lower() != "none"

    def is_addressed_to(self, agent_name: str) -> bool:
        """Check whether this envelope targets a specific agent."""
        target = (self.to or self.target or "").lower()
        if agent_name.lower() in target:
            return True
        if self.context_box and self.context_box.get("waiting_on", "").lower() == agent_name.lower():
            return True
        if agent_name.lower() in self.subject.lower() and self.should_reply():
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Drop None values for cleaner payload
        return {k: v for k, v in d.items() if v is not None}

    def render(self, prefix_banana: bool = True) -> str:
        """Render the envelope as a fenced code block."""
        body = json.dumps(self.to_dict(), indent=2)
        prefix = "🍌 " if prefix_banana else ""
        return f"{prefix}```handoff\n{body}\n```"

def parse_envelope(text: str) -> Optional[HandoffEnvelope]:
    """Extract and parse the ```handoff ... ``` JSON envelope from message text."""
    if not text:
        return None
    m = re.search(r"```handoff\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not m:
        return None
    try:
        raw = json.loads(m.group(1))
        return HandoffEnvelope(
            v=raw.get("v", 0),
            kind=raw.get("kind", "answer"),
            reply=raw.get("reply", "optional"),
            subject=raw.get("subject", ""),
            evidence=raw.get("evidence", []),
            supersedes=raw.get("supersedes"),
            context_box=raw.get("context_box"),
            to=raw.get("to"),
            target=raw.get("target")
        )
    except Exception:
        return None

def format_envelope(
    kind: str = "answer",
    reply: str = "optional",
    subject: str = "",
    evidence: Optional[List[Dict[str, str]]] = None,
    context_box: Optional[Dict[str, Any]] = None,
    supersedes: Optional[str] = None,
    prefix_banana: bool = True
) -> str:
    """Convenience helper to format a fenced handoff JSON block."""
    env = HandoffEnvelope(
        v=0,
        kind=kind,
        reply=reply,
        subject=subject,
        evidence=evidence or [],
        context_box=context_box,
        supersedes=supersedes
    )
    return env.render(prefix_banana=prefix_banana)
