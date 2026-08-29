# Agent Handoff Envelope Specification (v0)

## Purpose
The handoff envelope is a standardized JSON fenced block format used for structured coordination, peer review, task delegation, and status communication between AI agents and human developers in Crab Cavern.

## Envelope Schema

```json
{
  "v": 0,
  "kind": "question" | "answer" | "status" | "proposal" | "correction" | "finding" | "handoff",
  "reply": "required" | "optional" | "none",
  "subject": "kebab-case-topic-identifier",
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

## Field Definitions
- **`v`**: Integer protocol version (currently `0`).
- **`kind`**: Communicative intent:
  - `question`: Inquires or requests analysis from peer.
  - `answer`: Supplies requested data or solution.
  - `status`: Broadcasts operational state without requiring peer intervention.
  - `proposal`: Suggests an architectural or code change.
  - `correction`: Corrects a mistaken assertion or broken state.
  - `finding`: Reports a diagnostic or benchmark result.
  - `handoff`: Passes execution baton to a designated peer.
- **`reply`**: Turn-reply gating:
  - `required`: Calling agent expects a follow-up response.
  - `optional`: Informational; reply if relevant.
  - `none`: **Unconditionally silent**. Peers must not post a reply.
- **`context_box`**: Turn claim lease metadata mirroring the Banana mutex state.
