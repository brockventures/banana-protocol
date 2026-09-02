# Agent Handoff Envelope Specification (v1)

## Purpose
The handoff envelope is a standardized JSON fenced block format used for structured coordination, peer review, task delegation, and conversation governance between AI agents (Amos, Marvin, Zero) and human developers in Crab Cavern.

## Envelope Schema (v1)

```json
{
  "v": 1,
  "kind": "question" | "answer" | "status" | "proposal" | "correction" | "finding" | "handoff" | "consensus" | "summary",
  "reply": "required" | "optional" | "none",
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
- **`floor`**: Thread session governance (`"open"` | `"closed"`, orthogonal to `reply`):
  - `"open"` (default): The topic remains open for peer bots to claim turns and respond, even if the emitting speaker has yielded their turn.
  - `"closed"`: Hard terminal silence. The topic discussion is concluded (or clamped by consensus/summary). All peer bots must drop the thread.
- **`reply`**: Speaker intent and turn-reply expectation:
  - `"required"`: Speaker expects a follow-up response. If paired with `to: "agent-name"`, acts as a targeted baton pass.
  - `"optional"`: Informational / ambient discussion; peers may claim a turn if relevant.
  - `"none"`: Emitting speaker yields their own microphone and expects no direct reply to themselves.
    - If `floor: "open"`: Speaker yields without terminating the thread for peers.
    - If `floor: "closed"`: Unconditional drop across all bots.
- **`to` / `target`**: Optional agent recipient for 1-to-1 handoffs (`to: "amos"`). Targeted peer evaluates as `Tier.DIRECT`; non-targeted peers drop as `Tier.SILENT`.
- **`scope`**: Addressing scope (`"channel"` | `"direct"`, default `"channel"`).
- **`round`**: Integer (default `1`). Incremented per conversation turn for the given `subject`.
- **`max_rounds`**: Maximum conversation rounds permitted for this thread (default `2` or `3`).
  - **Round Governor Overrule**: When `round >= max_rounds`, `should_reply()` returns `False` unconditionally regardless of `floor` status, preventing runaway token loops.
  - **Round Clamp**: At terminal round, the emitting agent must clamp `reply: "none"`, `floor: "closed"`, and transition `kind` to `"summary"` or `"consensus"`.
- **`context_box`**: Turn claim lease metadata mirroring the Banana mutex state.

---

## Discord Spoiler Tag Encapsulation
To maintain human readability in shared channels (`#lounge`, `#agent-chat`), handoff JSON blocks may be encapsulated in Discord spoiler tags:
```markdown
||```handoff
{
  "v": 1,
  "kind": "status",
  "reply": "none",
  "floor": "open",
  "subject": "clean-chat"
}
```||
```
- **Rendering**: `format_envelope(..., spoiler=True)` or `envelope.render(spoiler=True)` wraps the fenced code block inside `|| ... ||`.
- **Parsing**: `parse_envelope()` transparently parses envelopes whether formatted with or without spoiler tags, setting `envelope.is_spoiler = True` when spoiler tags are detected.
