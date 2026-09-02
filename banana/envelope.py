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
    v: int = 1
    kind: str = "answer"              # "question" | "answer" | "status" | "proposal" | "correction" | "finding" | "handoff" | "consensus" | "summary"
    reply: str = "open"               # "open" | "baton" | "none" (legacy: "required" | "optional")
    floor: str = "open"               # "open" | "closed"
    scope: str = "channel"            # "channel" | "direct"
    subject: str = ""
    round: int = 1
    max_rounds: int = 2
    evidence: List[Dict[str, str]] = field(default_factory=list)
    supersedes: Optional[str] = None
    context_box: Optional[Dict[str, Any]] = None
    to: Optional[str] = None
    target: Optional[str] = None

    @property
    def is_soft_terminal(self) -> bool:
        """Returns True if the envelope has reached the soft round limit (>= max_rounds)."""
        return self.round >= self.max_rounds

    def should_reply(self, agent_name: Optional[str] = None, max_rounds: Optional[int] = None) -> bool:
        """
        Evaluate whether an agent should reply to this envelope.
        - Returns False if floor is explicitly 'closed'.
        - Returns False if round limit is reached (round >= max_rounds).
        - If reply is 'baton', returns True only if targeted to agent_name.
        - If reply is 'none':
            - If floor is 'closed', returns False.
            - If floor is 'open':
                - If agent_name matches current holder/emitter in context_box, returns False (speaker yielded).
                - Otherwise returns True (floor remains open for peers).
        - If reply is 'open' (or legacy 'optional'): returns True while floor is open and round limit not exceeded.
        """
        limit = max_rounds if max_rounds is not None else self.max_rounds
        if self.floor.lower() == "closed":
            return False
        if self.round >= limit:
            return False

        reply_val = self.reply.lower()

        if reply_val == "baton":
            if agent_name:
                return self.is_addressed_to(agent_name)
            return bool(self.to or self.target)

        if reply_val == "none":
            if self.floor.lower() == "open":
                if agent_name and self.context_box:
                    holder = (self.context_box.get("holder") or "").lower()
                    if holder and agent_name.lower() == holder:
                        return False
                return True
            return False

        if reply_val == "required":
            if (self.to or self.target) and agent_name:
                return self.is_addressed_to(agent_name)
            return True

        return True

    def clamp_terminal(self, kind: str = "summary") -> "HandoffEnvelope":
        """Clamp envelope into terminal state (reply: none, floor: closed, kind: summary/consensus)."""
        self.reply = "none"
        self.floor = "closed"
        self.kind = kind
        return self

    def is_addressed_to(self, agent_name: str) -> bool:
        """Check whether this envelope targets a specific agent."""
        if not agent_name:
            return False
        target = (self.to or self.target or "").lower()
        if agent_name.lower() in target:
            return True
        if self.context_box and (self.context_box.get("waiting_on") or "").lower() == agent_name.lower():
            return True
        if agent_name.lower() in self.subject.lower() and self.should_reply(agent_name):
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
        reply = raw.get("reply", "open" if raw.get("v", 0) >= 1 else "optional")
        floor = raw.get("floor")
        if floor is None:
            floor = "closed" if str(reply).lower() == "none" else "open"

        return HandoffEnvelope(
            v=raw.get("v", 1 if "v" in raw else 0),
            kind=raw.get("kind", "answer"),
            reply=str(reply),
            floor=str(floor),
            scope=raw.get("scope", "channel"),
            subject=raw.get("subject", ""),
            round=raw.get("round", 1),
            max_rounds=raw.get("max_rounds", 2),
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
    reply: str = "open",
    floor: Optional[str] = None,
    scope: str = "channel",
    subject: str = "",
    round: int = 1,
    max_rounds: int = 2,
    evidence: Optional[List[Dict[str, str]]] = None,
    context_box: Optional[Dict[str, Any]] = None,
    supersedes: Optional[str] = None,
    to: Optional[str] = None,
    target: Optional[str] = None,
    prefix_banana: bool = True,
    v: int = 1
) -> str:
    """Convenience helper to format a fenced handoff JSON block."""
    if floor is None:
        floor = "closed" if reply.lower() == "none" else "open"
    env = HandoffEnvelope(
        v=v,
        kind=kind,
        reply=reply,
        floor=floor,
        scope=scope,
        subject=subject,
        round=round,
        max_rounds=max_rounds,
        evidence=evidence or [],
        context_box=context_box,
        supersedes=supersedes,
        to=to,
        target=target
    )
    return env.render(prefix_banana=prefix_banana)

def should_reply(envelope_or_text: Any, agent_name: Optional[str] = None, max_rounds: Optional[int] = None) -> bool:
    """
    Canonical helper to evaluate whether an agent should reply to an envelope or raw text.
    Decouples local speaker yield (reply: none) from floor termination (floor: closed / max_rounds).
    """
    if isinstance(envelope_or_text, HandoffEnvelope):
        return envelope_or_text.should_reply(agent_name=agent_name, max_rounds=max_rounds)
    if isinstance(envelope_or_text, str):
        env = parse_envelope(envelope_or_text)
        if not env:
            return True
        return env.should_reply(agent_name=agent_name, max_rounds=max_rounds)
    return True
