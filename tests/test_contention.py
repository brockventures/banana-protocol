import unittest
from unittest.mock import patch, MagicMock
from banana.client import BananaClient, AsyncBananaClient, BananaBlockedError

class TestContentionLogic(unittest.TestCase):
    def test_preflight_blocks_when_other_agent_holds(self):
        client = BananaClient(holder="zero", token="mock-token")
        with patch.object(client, "get_status", return_value={"holder": "marvin", "state": {"id": 1, "holder": "marvin"}}):
            with self.assertRaises(BananaBlockedError) as ctx:
                client.claim("test-task", preflight=True)
            self.assertEqual(ctx.exception.current_holder, "marvin")

    def test_preflight_allows_same_agent_reentrancy(self):
        client = BananaClient(holder="zero", token="mock-token")
        with patch.object(client, "get_status", return_value={"holder": "zero", "state": {"id": 1, "holder": "zero"}}):
            with patch("urllib.request.urlopen") as mock_open:
                mock_resp = MagicMock()
                mock_resp.read.return_value = b'{"ok": true, "state": {"holder": "zero"}}'
                mock_resp.__enter__.return_value = mock_resp
                mock_open.return_value = mock_resp
                res = client.claim("test-task", preflight=True)
                self.assertTrue(res.get("ok"))

    def test_context_manager_always_releases_on_exception(self):
        client = BananaClient(holder="zero", token="mock-token")
        with patch.object(client, "claim", return_value={"ok": True}) as mock_claim:
            with patch.object(client, "release", return_value={"ok": True}) as mock_release:
                with self.assertRaises(RuntimeError):
                    with client.hold("crash-test", preflight=False):
                        raise RuntimeError("simulated mid-turn crash")
                mock_claim.assert_called_once()
                mock_release.assert_called_once()

if __name__ == "__main__":
    unittest.main()
