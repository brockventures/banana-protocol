# Agent Handoff Envelope Specification (v1)

## Purpose
The handoff envelope is a standardized JSON fenced block format used for structured coordination, peer review, task delegation, and conversation governance between AI agents (Amos, Marvin, Zero) and human developers in Crab Cavern.

## Envelope Schema (v1)

```json
{
  "v": 1,
  "kind": "question" | "answer" | "status" | "proposal" | "correction" | "finding" | "handoff" | "consensus" | "summary",
  "reply": "required" | "optional" | "none",
  "subject": "kebab-case-topic-identifier",
  "round": 1,
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
- **`reply`**: Turn-reply gating:
  - `required`: Calling agent expects a follow-up response.
  - `optional`: Informational; reply if relevant.
  - `none`: **Unconditionally silent**. Peers must not post a reply.
- **`round`**: Integer (default `1`). Incremented per conversation turn for the given `subject`.
  - **Round 1**: Initial inquiry / proposal (`reply: required` or `optional`).
  - **Round 2**: Rebuttal / response.
  - **Round 2 Terminal Clamp**: When `round >= 2`, the emitting agent must clamp `reply: "none"` and transition `kind` to `"summary"` or `"consensus"`.
- **`context_box`**: Turn claim lease metadata mirroring the Banana mutex state.
