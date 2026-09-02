"""
tests/test_heartbeat.py - Tests for the client-side heartbeat helper
(banana-protocol issue #2): BananaClient.heartbeat()/start_heartbeat()/
stop_heartbeat() and the AsyncBananaClient equivalents, plus the
heartbeat_interval convenience on hold().
"""

import asyncio
import json
import time
import unittest
import urllib.error
from unittest.mock import patch, MagicMock

from banana.client import BananaClient, AsyncBananaClient, BananaError


def _mock_urlopen(response_body: dict, status: int = 200):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_body).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


class TestHeartbeatSync(unittest.TestCase):
    def test_heartbeat_sends_holder_and_generation(self):
        client = BananaClient(holder="amos", token="tok")
        client._generation = 7
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen(
                {"ok": True, "renewed": True, "state": {"holder": "amos", "generation": 7}}
            )
            result = client.heartbeat()
            self.assertTrue(result["renewed"])
            sent = json.loads(mock_open.call_args[0][0].data.decode("utf-8"))
            self.assertEqual(sent, {"holder": "amos", "generation": 7})
            self.assertTrue(mock_open.call_args[0][0].full_url.endswith("/heartbeat"))

    def test_heartbeat_omits_generation_when_none_captured(self):
        client = BananaClient(holder="amos", token="tok")
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen({"ok": True, "renewed": True, "state": {}})
            client.heartbeat()
            sent = json.loads(mock_open.call_args[0][0].data.decode("utf-8"))
            self.assertEqual(sent, {"holder": "amos"})

    def test_heartbeat_requires_token(self):
        client = BananaClient(holder="amos", token=None)
        with self.assertRaises(BananaError):
            client.heartbeat()

    def test_heartbeat_raises_on_stale_generation(self):
        client = BananaClient(holder="amos", token="tok")
        client._generation = 3
        error_body = json.dumps({
            "ok": False, "renewed": False,
            "error": {"code": "stale_generation", "message": "stale"},
        }).encode("utf-8")
        http_err = urllib.error.HTTPError(
            url="https://banana.mikecarmody.net/api/heartbeat", code=409,
            msg="Conflict", hdrs={"Content-Type": "application/json"},
            fp=None,
        )
        http_err.read = lambda: error_body
        with patch("urllib.request.urlopen", side_effect=http_err):
            with self.assertRaises(BananaError):
                client.heartbeat()

    def test_start_stop_heartbeat_calls_on_interval(self):
        client = BananaClient(holder="amos", token="tok")
        calls = []
        client.heartbeat = lambda: calls.append(time.time())
        client.start_heartbeat(interval=0.05)
        time.sleep(0.23)
        client.stop_heartbeat()
        count_after_stop = len(calls)
        time.sleep(0.15)
        # No further calls after stop_heartbeat() joined the thread.
        self.assertEqual(len(calls), count_after_stop)
        self.assertGreaterEqual(count_after_stop, 2)
        self.assertIsNone(client._heartbeat_thread)
        self.assertIsNone(client._heartbeat_stop)

    def test_start_heartbeat_swallows_errors(self):
        client = BananaClient(holder="amos", token="tok")
        client.heartbeat = MagicMock(side_effect=BananaError("not_holder"))
        client.start_heartbeat(interval=0.05)
        time.sleep(0.12)
        client.stop_heartbeat()  # must not raise despite heartbeat() always failing
        self.assertGreaterEqual(client.heartbeat.call_count, 1)

    def test_stop_heartbeat_is_a_noop_without_start(self):
        client = BananaClient(holder="amos", token="tok")
        client.stop_heartbeat()  # should not raise

    def test_release_stops_heartbeat(self):
        client = BananaClient(holder="amos", token="tok")
        client.start_heartbeat(interval=30.0)
        thread = client._heartbeat_thread
        self.assertIsNotNone(thread)
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen({"ok": True, "released": True, "state": {}})
            client.release()
        self.assertIsNone(client._heartbeat_thread)
        self.assertFalse(thread.is_alive())

    def test_hold_with_heartbeat_interval_starts_and_stops(self):
        client = BananaClient(holder="amos", token="tok")
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen(
                {"ok": True, "state": {"holder": "amos"}, "conflict": None, "generation": 1}
            )
            with client.hold("subject", preflight=False, heartbeat_interval=30.0):
                self.assertIsNotNone(client._heartbeat_thread)
            self.assertIsNone(client._heartbeat_thread)

    def test_hold_without_heartbeat_interval_never_starts_one(self):
        client = BananaClient(holder="amos", token="tok")
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen(
                {"ok": True, "state": {"holder": "amos"}, "conflict": None, "generation": 1}
            )
            with client.hold("subject", preflight=False):
                self.assertIsNone(client._heartbeat_thread)


class _AsyncMockResponse:
    def __init__(self, body, status=200):
        self._body = body
        self.status = status

    async def json(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _AsyncMockSession:
    def __init__(self, response):
        self._response = response

    def post(self, *args, **kwargs):
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class TestHeartbeatAsync(unittest.IsolatedAsyncioTestCase):
    async def test_heartbeat_sends_generation(self):
        client = AsyncBananaClient(holder="zero", token="tok")
        client._generation = 4
        resp = _AsyncMockResponse({"ok": True, "renewed": True, "state": {"generation": 4}})
        captured = {}

        class _Session(_AsyncMockSession):
            def post(self, url, json=None, **kwargs):
                captured["url"] = url
                captured["json"] = json
                return resp

        with patch("aiohttp.ClientSession", return_value=_Session(resp)):
            result = await client.heartbeat()
        self.assertTrue(result["renewed"])
        self.assertTrue(captured["url"].endswith("/heartbeat"))
        self.assertEqual(captured["json"], {"holder": "zero", "generation": 4})

    async def test_heartbeat_requires_token(self):
        client = AsyncBananaClient(holder="zero", token=None)
        with self.assertRaises(BananaError):
            await client.heartbeat()

    async def test_start_stop_heartbeat_task(self):
        client = AsyncBananaClient(holder="zero", token="tok")
        calls = []

        async def fake_heartbeat():
            calls.append(1)
            return {"ok": True}

        client.heartbeat = fake_heartbeat
        client.start_heartbeat(interval=0.05)
        await asyncio.sleep(0.23)
        await client.stop_heartbeat()
        self.assertGreaterEqual(len(calls), 2)
        self.assertIsNone(client._heartbeat_task)

    async def test_release_stops_heartbeat_task(self):
        client = AsyncBananaClient(holder="zero", token="tok")

        async def fake_heartbeat():
            return {"ok": True}

        client.heartbeat = fake_heartbeat
        client.start_heartbeat(interval=30.0)
        self.assertIsNotNone(client._heartbeat_task)
        resp = _AsyncMockResponse({"ok": True, "released": True, "state": {}})
        with patch("aiohttp.ClientSession", return_value=_AsyncMockSession(resp)):
            await client.release()
        self.assertIsNone(client._heartbeat_task)


if __name__ == "__main__":
    unittest.main()
