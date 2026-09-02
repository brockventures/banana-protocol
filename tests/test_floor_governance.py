import unittest
from banana.envelope import HandoffEnvelope, parse_envelope, format_envelope, should_reply
from banana.classifier import IngestionClassifier, Tier, Event

class TestFloorGovernance(unittest.TestCase):
    def test_decoupled_speaker_yield_allows_peers_to_continue(self):
        """When an agent yields (reply: none, floor: open), peers can continue the thread."""
        env = HandoffEnvelope(
            v=1,
            kind="answer",
            reply="none",
            floor="open",
            subject="shared-store-concurrency",
            round=1,
            context_box={"holder": "amos"}
        )
        rendered = env.render()
        parsed = parse_envelope(rendered)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.reply, "none")
        self.assertEqual(parsed.floor, "open")

        # Emitting agent (Amos) has yielded their turn
        self.assertFalse(parsed.should_reply(agent_name="amos"))

        # Peer agent (Zero) sees open floor and can continue
        self.assertTrue(parsed.should_reply(agent_name="zero"))

        # Classifier evaluates peer as CLASSIFIED (evaluating whether to claim turn)
        classifier = IngestionClassifier(agent_name="zero")
        ev = Event(sender="Amos", content=rendered)
        self.assertEqual(classifier.evaluate(ev), Tier.CLASSIFIED)

        # Emitting agent classifier treats it as SILENT
        amos_classifier = IngestionClassifier(agent_name="amos")
        self.assertEqual(amos_classifier.evaluate(ev), Tier.SILENT)

    def test_floor_closed_unconditional_silence(self):
        """When floor is closed (consensus/summary), all agents remain silent."""
        env = HandoffEnvelope(
            v=1,
            kind="consensus",
            reply="none",
            floor="closed",
            subject="shared-store-concurrency",
            round=2
        )
        self.assertFalse(env.should_reply(agent_name="zero"))
        self.assertFalse(env.should_reply(agent_name="amos"))

        classifier = IngestionClassifier(agent_name="zero")
        ev = Event(sender="Amos", content=env.render())
        self.assertEqual(classifier.evaluate(ev), Tier.SILENT)

    def test_round_governor_overrules_open_floor(self):
        """Round quota terminates discussion even if floor is marked open."""
        env = HandoffEnvelope(
            v=1,
            kind="answer",
            reply="open",
            floor="open",
            subject="infinite-debate",
            round=3,
            max_rounds=3
        )
        self.assertFalse(env.should_reply(agent_name="zero"))
        self.assertTrue(env.is_soft_terminal)

        classifier = IngestionClassifier(agent_name="zero")
        ev = Event(sender="Amos", content=env.render())
        self.assertEqual(classifier.evaluate(ev), Tier.SILENT)

    def test_baton_intent_routes_directly_to_target(self):
        """reply: baton with to: peer gives DIRECT to peer and SILENT to non-targets."""
        env = HandoffEnvelope(
            v=1,
            kind="handoff",
            reply="baton",
            floor="open",
            to="amos",
            subject="wal-implementation",
            round=1
        )
        rendered = env.render()
        parsed = parse_envelope(rendered)

        # Targeted agent (Amos)
        self.assertTrue(parsed.should_reply(agent_name="amos"))
        amos_classifier = IngestionClassifier(agent_name="amos")
        self.assertEqual(amos_classifier.evaluate(Event(sender="Zero", content=rendered)), Tier.DIRECT)

        # Non-targeted agent (Marvin)
        self.assertFalse(parsed.should_reply(agent_name="marvin"))
        marvin_classifier = IngestionClassifier(agent_name="marvin")
        self.assertEqual(marvin_classifier.evaluate(Event(sender="Zero", content=rendered)), Tier.SILENT)

    def test_package_level_should_reply_helper(self):
        """banana.should_reply works with text and HandoffEnvelope instances."""
        text = """🍌 ```handoff
{
  "v": 1,
  "kind": "answer",
  "reply": "none",
  "floor": "open",
  "subject": "quick-helper-test",
  "round": 1,
  "context_box": {"holder": "marvin"}
}
```"""
        self.assertTrue(should_reply(text, agent_name="zero"))
        self.assertFalse(should_reply(text, agent_name="marvin"))

    def test_backward_compatibility_defaults(self):
        """Omitted floor on reply: none defaults to closed (v0 behavior)."""
        legacy_none = """```handoff
{
  "v": 0,
  "kind": "status",
  "reply": "none",
  "subject": "legacy-post"
}
```"""
        env = parse_envelope(legacy_none)
        self.assertEqual(env.floor, "closed")
        self.assertFalse(env.should_reply(agent_name="zero"))

        legacy_opt = """```handoff
{
  "v": 0,
  "kind": "question",
  "reply": "optional",
  "subject": "legacy-question"
}
```"""
        env_opt = parse_envelope(legacy_opt)
        self.assertEqual(env_opt.floor, "open")
        self.assertTrue(env_opt.should_reply(agent_name="zero"))

if __name__ == "__main__":
    unittest.main()
