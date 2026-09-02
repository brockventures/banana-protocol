"""
tests/test_v4_features.py - Tests for v0.4.0 Crab Cavern coordination features:
1. Discord spoiler tags for handoff envelopes (||```handoff...```||).
2. Client-side subject cache preserving topic continuity across turns.
3. 2-minute (120s) floor lease ceiling and expiration helpers.
"""

import json
import time
import unittest
from unittest.mock import patch, MagicMock

from banana.envelope import HandoffEnvelope, parse_envelope, format_envelope
from banana.client import (
    BananaClient,
    AsyncBananaClient,
    SubjectCache,
    DEFAULT_LEASE_TTL_SECONDS,
)


def _mock_urlopen(response_body: dict):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_body).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


class TestSpoilerTags(unittest.TestCase):
    def test_render_with_spoiler(self):
        env = HandoffEnvelope(
            kind="proposal",
            reply="required",
            subject="architecture-review",
            is_spoiler=True,
        )
        rendered = env.render(prefix_banana=True)
        self.assertTrue(rendered.startswith("🍌 ||```handoff\n"))
        self.assertTrue(rendered.endswith("\n```||"))
        self.assertNotIn("is_spoiler", rendered)

    def test_format_envelope_with_spoiler(self):
        rendered = format_envelope(
            kind="answer",
            reply="none",
            subject="spoiler-test",
            spoiler=True,
            prefix_banana=False,
        )
        self.assertTrue(rendered.startswith("||```handoff\n"))
        self.assertTrue(rendered.endswith("\n```||"))

    def test_parse_spoiler_wrapped_envelope(self):
        text = """Here is the hidden payload:
||```handoff
{
  "v": 1,
  "kind": "status",
  "reply": "none",
  "floor": "closed",
  "subject": "quiet-room"
}
```||
That's it."""
        env = parse_envelope(text)
        self.assertIsNotNone(env)
        self.assertTrue(env.is_spoiler)
        self.assertEqual(env.subject, "quiet-room")
        self.assertEqual(env.floor, "closed")

    def test_parse_regular_envelope_is_not_spoiler(self):
        text = """```handoff
{
  "v": 1,
  "kind": "question",
  "reply": "required",
  "subject": "open-room"
}
```"""
        env = parse_envelope(text)
        self.assertIsNotNone(env)
        self.assertFalse(env.is_spoiler)
        self.assertEqual(env.subject, "open-room")


class TestSubjectCache(unittest.TestCase):
    def test_standalone_cache(self):
        cache = SubjectCache()
        self.assertIsNone(cache.get())
        cache.set("feature-auth")
        self.assertEqual(cache.get(), "feature-auth")
        self.assertEqual(cache.last_subject, "feature-auth")

        # Keyed cache
        cache.set("feature-db", key="backend")
        self.assertEqual(cache.get("backend"), "feature-db")
        self.assertIsNone(cache.get("other"))

        cache.clear("backend")
        self.assertIsNone(cache.get("backend"))

    def test_sync_client_subject_caching(self):
        client = BananaClient(holder="zero", token="mock-token")
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _mock_urlopen({"ok": True, "subject": captured["body"].get("subject", "")})

        # Turn 1: Explicit subject passed
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.claim("distributed-tracing", preflight=False)
        self.assertEqual(captured["body"]["subject"], "distributed-tracing")
        self.assertEqual(client.get_cached_subject(), "distributed-tracing")

        # Turn 2: Empty subject passed -> falls back to cached subject
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.claim("", preflight=False)
        self.assertEqual(captured["body"]["subject"], "distributed-tracing")

        # Turn 3: Explicit new subject overrides
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.claim("new-topic", preflight=False)
        self.assertEqual(captured["body"]["subject"], "new-topic")
        self.assertEqual(client.get_cached_subject(), "new-topic")

        # Clear cache
        client.clear_subject_cache()
        self.assertIsNone(client.get_cached_subject())


class TestAsyncSubjectCache(unittest.IsolatedAsyncioTestCase):
    async def test_async_client_subject_caching(self):
        client = AsyncBananaClient(holder="amos", token="mock-token")
        captured = {}

        class FakeResp:
            status = 200
            async def json(self):
                return {"ok": True, "subject": captured.get("subject", "")}
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                return False

        class FakeSession:
            def post(self, url, json=None, **k):
                captured["subject"] = json.get("subject")
                return FakeResp()
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                return False

        with patch("aiohttp.ClientSession", return_value=FakeSession()):
            await client.claim("async-coordination", preflight=False)
        self.assertEqual(captured["subject"], "async-coordination")
        self.assertEqual(client.get_cached_subject(), "async-coordination")

        # Subsequent claim with empty subject reuses cached topic
        with patch("aiohttp.ClientSession", return_value=FakeSession()):
            await client.claim("", preflight=False)
        self.assertEqual(captured["subject"], "async-coordination")


class TestTwoMinuteLeaseTTL(unittest.TestCase):
    def test_default_ttl_constant(self):
        self.assertEqual(DEFAULT_LEASE_TTL_SECONDS, 120)
        client = BananaClient(holder="zero")
        self.assertEqual(client.lease_ttl, 120)

    def test_is_lease_expired_calculation(self):
        now = 1000.0
        # 60s ago: active (< 120s)
        active_state = {"claimed_at": 940.0, "holder": "zero"}
        self.assertFalse(BananaClient.is_lease_expired(active_state, current_time=now))

        # 121s ago: expired (> 120s)
        expired_state = {"claimed_at": 879.0, "holder": "zero"}
        self.assertTrue(BananaClient.is_lease_expired(expired_state, current_time=now))

        # Check last_active_ts takes priority
        renewed_state = {"claimed_at": 800.0, "last_active_ts": 950.0, "holder": "zero"}
        self.assertFalse(BananaClient.is_lease_expired(renewed_state, current_time=now))


if __name__ == "__main__":
    unittest.main()
