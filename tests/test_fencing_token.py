"""Fencing-token behavior (Kleppmann's Redlock critique): a claim response's
`state.id` should be captured and echoed back on release, so a server that
validates it can reject a stale release from a holder that lost the lock
without ever finding out. Purely additive — a server with no `generation`
concept just ignores the extra field.
"""
import json
import unittest
from unittest.mock import patch, MagicMock

from banana.client import BananaClient, AsyncBananaClient


def _mock_urlopen(response_body: dict):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_body).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


class TestFencingTokenSync(unittest.TestCase):
    def test_claim_captures_generation_from_state_id(self):
        client = BananaClient(holder="zero", token="mock-token")
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(
            {"ok": True, "state": {"id": 7, "holder": "zero"}}
        )):
            client.claim("test-task", preflight=False)
        self.assertEqual(client._generation, 7)

    def test_claim_with_no_generation_in_response_leaves_it_none(self):
        client = BananaClient(holder="zero", token="mock-token")
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(
            {"ok": True, "state": {"holder": "zero"}}
        )):
            client.claim("test-task", preflight=False)
        self.assertIsNone(client._generation)

    def test_release_echoes_captured_generation(self):
        client = BananaClient(holder="zero", token="mock-token")
        client._generation = 7
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _mock_urlopen({"ok": True, "released": True})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.release()
        self.assertEqual(captured["body"], {"holder": "zero", "generation": 7})

    def test_release_omits_generation_when_none_captured(self):
        client = BananaClient(holder="zero", token="mock-token")
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _mock_urlopen({"ok": True, "released": True})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.release()
        self.assertEqual(captured["body"], {"holder": "zero"})
        self.assertNotIn("generation", captured["body"])

    def test_release_clears_generation_after_success(self):
        client = BananaClient(holder="zero", token="mock-token")
        client._generation = 7
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(
            {"ok": True, "released": True}
        )):
            client.release()
        self.assertIsNone(client._generation)

    def test_extract_generation_prefers_top_level_generation_field(self):
        # Forward-compat: if a future server version returns `generation`
        # directly rather than `state.id`, prefer it.
        got = BananaClient._extract_generation({"generation": 42, "state": {"id": 1}})
        self.assertEqual(got, 42)


class TestFencingTokenAsync(unittest.IsolatedAsyncioTestCase):
    async def test_claim_captures_generation_from_state_id(self):
        client = AsyncBananaClient(holder="marvin", token="mock-token")

        class FakeResp:
            status = 200
            async def json(self):
                return {"ok": True, "state": {"id": 3, "holder": "marvin"}}
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                return False

        class FakeSession:
            def post(self, *a, **k):
                return FakeResp()
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                return False

        with patch("aiohttp.ClientSession", return_value=FakeSession()):
            await client.claim("test-task", preflight=False)
        self.assertEqual(client._generation, 3)

    async def test_release_echoes_captured_generation(self):
        client = AsyncBananaClient(holder="marvin", token="mock-token")
        client._generation = 3
        captured = {}

        class FakeResp:
            status = 200
            async def json(self):
                return {"ok": True, "released": True}
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                return False

        class FakeSession:
            def post(self, url, json=None, **k):
                captured["body"] = json
                return FakeResp()
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                return False

        with patch("aiohttp.ClientSession", return_value=FakeSession()):
            await client.release()
        self.assertEqual(captured["body"], {"holder": "marvin", "generation": 3})
        self.assertIsNone(client._generation)


if __name__ == "__main__":
    unittest.main()
