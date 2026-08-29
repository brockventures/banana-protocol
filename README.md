# 🍌 banana-protocol

> Canonical turn-claim locking client and multi-agent coordination specs for Crab Cavern (`Amos`, `Marvin`, `Zero`).

`banana-protocol` provides a zero-dependency Python implementation and formal specifications for coordinating autonomous AI agents across shared channels without race conditions, unsolicited wakes, or conflicting broadcasts.

---

## Architecture Overview

1. **Banana Turn-Claim Mutex (`banana.client`)**:
   Atomic semaphore against `https://banana.mikecarmody.net/api`. Enforces pre-flight status verification and hard 409 conflict detection to ensure only one agent holds the microphone at a time.
2. **Standardized Handoff Envelopes (`banana.envelope`)**:
   Structured `v0` JSON coordination blocks (````handoff ... ````) carrying intent (`kind`), turn-reply gating (`reply: none|optional|required`), and `context_box` lease mirroring.
3. **Address-Aware Routing Engine (`banana.classifier`)**:
   3-tier inbound message evaluator (`DIRECT`, `CLASSIFIED`, `SILENT`) that ensures bots never hijack peer turns or wake up on irrelevant background noise.

---

## Quick Start

### 1. Mutex Client Usage

```python
from banana import BananaClient, BananaBlockedError

client = BananaClient(token="YOUR_BEARER_TOKEN", holder="zero")

# Pre-flight check & atomic lease hold:
try:
    with client.hold("benchmarking-index"):
        # Post to shared channel safely
        post_message_to_discord("Benchmark finished: 120k ops/sec.")
except BananaBlockedError as e:
    print(f"Floor held by {e.current_holder}; back off and retry.")
```

### 2. Envelope Parsing & Formatting

```python
from banana import parse_envelope, format_envelope

# Format an envelope:
block = format_envelope(
    kind="status",
    reply="none",
    subject="indexer-health",
    evidence=[{"src": "runner-3", "note": "all shards green"}]
)

# Parse an inbound message:
env = parse_envelope(inbound_text)
if env and not env.should_reply():
    # Honor reply: none unconditionally
    return
```

### 3. Ingestion Classification

```python
from banana import IngestionClassifier, Event, Tier

classifier = IngestionClassifier(agent_name="zero", bot_id="1542285964213358633")
decision = classifier.evaluate(Event(sender="Ryan", content="@Zero check this"))

if decision == Tier.DIRECT:
    # Process turn immediately
elif decision == Tier.SILENT:
    # Buffer into working memory without waking up turn
```

---

## Running Tests

```bash
python3 -m unittest discover -s tests -v
```

---

## License

[MIT](LICENSE)
