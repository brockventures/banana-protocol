import unittest
import urllib.error
import io
import json
from unittest.mock import patch, MagicMock

from banana.client import (
    BananaClient,
    BananaBlockedError,
    BananaRoundLimitExceededError,
    BananaError
)
from banana.envelope import (
    HandoffEnvelope,
    parse_envelope,
    format_envelope
)

class TestRoundTracking(unittest.TestCase):

    def test_envelope_round_field(self):
        env = HandoffEnvelope(
            v=1,
            kind="proposal",
            reply="optional",
            subject="governor-rfc",
            round=2
        )
        rendered = env.render()
        self.assertIn('"round": 2', rendered)
        self.assertIn('"v": 1', rendered)

        parsed = parse_envelope(rendered)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.round, 2)
        self.assertEqual(parsed.v, 1)

    def test_format_envelope_round(self):
        rendered = format_envelope(
            kind="summary",
            reply="none",
            subject="governor-consensus",
            round=2
        )
        self.assertIn('"round": 2', rendered)
        self.assertIn('"reply": "none"', rendered)
        parsed = parse_envelope(rendered)
        self.assertEqual(parsed.round, 2)
        self.assertFalse(parsed.should_reply())

    def test_client_429_round_limit_exceeded(self):
        client = BananaClient(holder="zero", token="dummy-token")
        
        error_body = json.dumps({
            "code": "round_limit_exceeded",
            "subject": "runaway-topic",
            "round": 11,
            "hard_limit": 10,
            "error": "Hard round limit exceeded"
        }).encode("utf-8")
        
        http_error = urllib.error.HTTPError(
            url="https://banana.mikecarmody.net/api/claim",
            code=429,
            msg="Too Many Requests",
            hdrs={"Content-Type": "application/json"},
            fp=io.BytesIO(error_body)
        )

        with patch("urllib.request.urlopen", side_effect=http_error):
            with self.assertRaises(BananaRoundLimitExceededError) as ctx:
                client.claim(subject="runaway-topic", preflight=False)
            
            self.assertEqual(ctx.exception.round, 11)
            self.assertEqual(ctx.exception.hard_limit, 10)
            self.assertEqual(ctx.exception.subject, "runaway-topic")

    def test_client_409_still_raises_blocked(self):
        client = BananaClient(holder="zero", token="dummy-token")
        
        error_body = json.dumps({
            "code": "blocked",
            "holder": "amos",
            "state": {"holder": "amos"}
        }).encode("utf-8")
        
        http_error = urllib.error.HTTPError(
            url="https://banana.mikecarmody.net/api/claim",
            code=409,
            msg="Conflict",
            hdrs={"Content-Type": "application/json"},
            fp=io.BytesIO(error_body)
        )

        with patch("urllib.request.urlopen", side_effect=http_error):
            with self.assertRaises(BananaBlockedError) as ctx:
                client.claim(subject="test-topic", preflight=False)
            
    def test_soft_limit_should_reply(self):
        # Round 1 should allow reply
        env_r1 = HandoffEnvelope(v=1, kind="proposal", reply="optional", subject="test-topic", round=1)
        self.assertFalse(env_r1.is_soft_terminal)
        self.assertTrue(env_r1.should_reply())

        # Round 2 is soft-terminal -> should_reply() returns False
        env_r2 = HandoffEnvelope(v=1, kind="answer", reply="optional", subject="test-topic", round=2)
        self.assertTrue(env_r2.is_soft_terminal)
        self.assertFalse(env_r2.should_reply())

    def test_clamp_terminal(self):
        env = HandoffEnvelope(v=1, kind="answer", reply="required", subject="test-topic", round=2)
        env.clamp_terminal(kind="consensus")
        self.assertEqual(env.reply, "none")
        self.assertEqual(env.kind, "consensus")
        self.assertFalse(env.should_reply())

    def test_classifier_soft_limit_silence(self):
        from banana.classifier import IngestionClassifier, Event, Tier
        classifier = IngestionClassifier(agent_name="zero")
        
        # Round 2 envelope in inbound message -> classified as SILENT by default
        event = Event(
            sender="Amos",
            content="""🍌 ```handoff
{
  "v": 1,
  "kind": "answer",
  "reply": "optional",
  "subject": "governor-test",
  "round": 2
}
```
Here is the conclusion."""
        )
        self.assertEqual(classifier.evaluate(event), Tier.SILENT)

if __name__ == "__main__":
    unittest.main()
