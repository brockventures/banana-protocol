import unittest
from banana.envelope import parse_envelope, format_envelope, HandoffEnvelope
from banana.classifier import IngestionClassifier, Tier, Event
from banana.client import BananaClient, BananaBlockedError

class TestHandoffEnvelope(unittest.TestCase):
    def test_parse_valid_envelope(self):
        sample = """Here is the report.
🍌 ```handoff
{
  "v": 0,
  "kind": "finding",
  "reply": "optional",
  "subject": "banana-claims-live",
  "evidence": [{"src": "api/status", "note": "verified"}],
  "context_box": {
    "holder": "zero",
    "claimed_at": 1788022205.384,
    "last_active_ts": 1788022205.384,
    "released": false
  }
}
```
All done."""
        env = parse_envelope(sample)
        self.assertIsNotNone(env)
        self.assertEqual(env.v, 0)
        self.assertEqual(env.kind, "finding")
        self.assertTrue(env.should_reply())
        self.assertEqual(env.subject, "banana-claims-live")
        self.assertEqual(env.context_box["holder"], "zero")

    def test_reply_none(self):
        sample = """```handoff
{
  "v": 0,
  "kind": "status",
  "reply": "none",
  "subject": "silent-update"
}
```"""
        env = parse_envelope(sample)
        self.assertIsNotNone(env)
        self.assertFalse(env.should_reply())

    def test_render_envelope(self):
        rendered = format_envelope(kind="proposal", reply="required", subject="test-subject", prefix_banana=True)
        self.assertTrue(rendered.startswith("🍌 ```handoff"))
        self.assertIn('"kind": "proposal"', rendered)
        self.assertIn('"reply": "required"', rendered)

class TestClassifier(unittest.TestCase):
    def setUp(self):
        self.classifier = IngestionClassifier(agent_name="zero", bot_id="1542285964213358633")

    def test_direct_mention(self):
        ev = Event(sender="Ryan", content="<@1542285964213358633> check this out")
        self.assertEqual(self.classifier.evaluate(ev), Tier.DIRECT)

    def test_direct_name(self):
        ev = Event(sender="Ryan", content="Hey Zero: can you build the repo?")
        self.assertEqual(self.classifier.evaluate(ev), Tier.DIRECT)

    def test_silent_reply_none(self):
        ev = Event(sender="Amos", content="""```handoff
{
  "v": 0,
  "kind": "status",
  "reply": "none",
  "subject": "no-response-needed"
}
```""")
        self.assertEqual(self.classifier.evaluate(ev), Tier.SILENT)

    def test_targeted_handoff(self):
        ev = Event(sender="Amos", content="""```handoff
{
  "v": 0,
  "kind": "question",
  "reply": "required",
  "to": "zero",
  "subject": "code-review"
}
```""")
        self.assertEqual(self.classifier.evaluate(ev), Tier.DIRECT)

    def test_unrelated_bot_chatter(self):
        ev = Event(sender="Marvin", is_bot=True, content="ok done")
        self.assertEqual(self.classifier.evaluate(ev), Tier.SILENT)

    def test_general_channel_discussion(self):
        ev = Event(sender="Ryan", content="I wonder what architecture we should choose for the backend storage layer.")
        self.assertEqual(self.classifier.evaluate(ev), Tier.CLASSIFIED)

if __name__ == "__main__":
    unittest.main()

class TestAsyncClientImport(unittest.TestCase):
    def test_async_client_structure(self):
        from banana.client import AsyncBananaClient
        client = AsyncBananaClient(token="mock", holder="marvin")
        self.assertEqual(client.holder, "marvin")
        self.assertTrue(hasattr(client, "hold"))
        self.assertTrue(hasattr(client, "claim"))
        self.assertTrue(hasattr(client, "release"))
        self.assertTrue(hasattr(client, "get_status"))
