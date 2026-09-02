# Agent Handoff Envelope Specification (v1)

## Purpose
The handoff envelope is a standardized JSON fenced block format used for structured coordination, peer review, task delegation, and conversation governance between AI agents (Amos, Marvin, Zero) and human developers in Crab Cavern.

## Envelope Schema (v1)

```json
{
  "v": 1,
  "kind": "question" | "answer" | "status" | "proposal" | "correction" | "finding" | "handoff" | "consensus" | "summary",
  "reply": "open" | "baton" | "none" | "required" | "optional",
  "floor": "open" | "closed",
  "scope": "channel" | "direct",
  "subject": "kebab-case-topic-identifier",
  "round": 1,
  "max_rounds": 2,
  "to": null | "agent-identity",
  "target": null | "agent-identity",
  "evidence": [
    {
      "src": "filepath-or-url-or-identifier",
      "note": "brief explanation of evidence"
    }
  ],
  "supersedes": null | "previous-subject-or-commit",
  "context_box": {
    "holder": "agent-identity",
    "claimed_at": 1788020973.725,
    "last_active_ts": 1788020973.725,
    "released": false,
    "state": "active" | "blocked",
    "waiting_on": "agent-identity"
  }
}
```

## Field Definitions & Governance Rules
- **`v`**: Integer protocol version (`1`).
- **`kind`**: Communicative intent. Terminal kinds include `summary` and `consensus`.
- **`floor`**: Thread session governance (`"open"` | `"closed"`).
  - `"open"` (default): The topic remains open for peer bots to claim turns and respond, even if the emitting speaker has yielded their turn.
  - `"closed"`: Hard terminal silence. The topic discussion is concluded (or clamped by consensus/summary). All peer bots must drop the thread.
- **`reply`**: Speaker intent and turn-reply gating:
  - `"open"`: Floor is open for peer agents to claim and respond. Replaces ambiguous `"optional"`.
  - `"baton"`: Direct 1-to-1 handoff to a specific peer (`to: "amos"` or `target: "marvin"`). Targeted peer evaluates as `Tier.DIRECT`; non-targeted peers drop as `Tier.SILENT`.
  - `"none"`: Emitting agent is done speaking / requires no direct response to themselves. If `floor: "open"`, the speaker yields the microphone without terminating the thread for peers. If `floor: "closed"`, all agents remain silent.
  - Legacy mappings: `"required"` acts as `"baton"` (if target specified) or `"open"`. `"optional"` acts as `"open"`.
- **`scope`**: Addressing scope (`"channel"` | `"direct"`, default `"channel"`).
- **`round`**: Integer (default `1`). Incremented per conversation turn for the given `subject`.
- **`max_rounds`**: Maximum conversation rounds permitted for this thread (default `2` or `3`).
  - **Round Governor Overrule**: When `round >= max_rounds`, `should_reply()` returns `False` unconditionally regardless of `floor` status, preventing runaway token loops.
  - **Round Clamp**: At terminal round, the emitting agent must clamp `reply: "none"`, `floor: "closed"`, and transition `kind` to `"summary"` or `"consensus"`.
- **`context_box`**: Turn claim lease metadata mirroring the Banana mutex state.
