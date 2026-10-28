# AGENTS.md — `banana-protocol`

> **B**inary **A**rbitration **N**ode **A**nd **N**on-blocking **A**cquisition — Canonical turn-claim client and multi-agent coordination library for Crab Cavern.

## Quick Verification & Pre-Flight One-Liner

```bash
ruff check banana/ tests/test_protocol.py && pytest tests/test_protocol.py && git status -s
```

## Module Map

- `banana/client.py`: Synchronous (`BananaClient`) and asynchronous (`AsyncBananaClient`) turn-claim mutex clients with fencing token validation, heartbeat renewal, and round-limit guards.
- `banana/envelope.py`: Parser (`parse_envelope`) and formatter (`format_envelope`) for `v0` and `v1.1` JSON `handoff` envelopes, including multi-recipient `to` normalization and kind aliasing.
- `banana/classifier.py`: 3-tier address-aware message router (`IngestionClassifier` returning `Tier.DIRECT`, `Tier.CLASSIFIED`, or `Tier.SILENT`).
- `specs/`: Protocol specifications (`agent-handoff-envelope-v0.md`, `agent-handoff-envelope-v1.md`, `banana-turn-claim-api.md`).

## Architectural Invariants

1. **Zero Runtime Dependencies (Core Sync Path):** `banana` core (`client.py` sync path, `envelope.py`, `classifier.py`) uses Python standard library only. `aiohttp` is lazily imported inside `AsyncBananaClient` methods.
2. **Envelope-less Bot Noise Suppression:** In `IngestionClassifier.evaluate()`, any inbound message from a bot (`event.is_bot=True`) lacking a parsed `HandoffEnvelope` (`env is None`) and lacking an explicit direct `@mention` (`<@bot_id>`) or direct reply (`is_reply_to_agent=True`) deterministically returns `Tier.SILENT`. Bots never wake peer classifiers via untagged or envelope-less prose.
3. **Human Broadcast Carve-Out:** Envelope-less messages from humans (`event.is_bot=False`) without direct mentions or vocative prefixes return `Tier.CLASSIFIED` so agents can evaluate open-room human questions via their semantic classifier.
4. **Vocative Name Anchor:** Plain-text name triggers at the start of a message (`Zero:`, `Hey Zero,`) only apply to human senders (`not event.is_bot`) and require an explicit vocative greeting, `@` prefix, or immediate punctuation (`[:,!?]`) so third-person references and possessives (`Zero's`) never falsely trigger `Tier.DIRECT`.
5. **Version Synchronization:** Keep `__version__` in `banana/__init__.py` and `version` in `pyproject.toml` strictly synchronized on every release bump.
