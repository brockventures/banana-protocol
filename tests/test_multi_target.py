import pytest
from banana.envelope import HandoffEnvelope, parse_envelope, format_envelope

def test_multi_recipient_list():
    env = HandoffEnvelope(to=["amos", "aerial"], reply="required")
    assert env.is_addressed_to("amos") is True
    assert env.is_addressed_to("aerial") is True
    assert env.is_addressed_to("zero") is False
    assert env.should_reply("aerial") is True
    assert env.should_reply("zero") is False

def test_broadcast_wildcard_team():
    env = HandoffEnvelope(to="team", reply="required")
    assert env.is_addressed_to("amos") is True
    assert env.is_addressed_to("aerial") is True
    assert env.is_addressed_to("zero") is True
    assert env.should_reply("aerial") is True

def test_broadcast_wildcard_all():
    env = HandoffEnvelope(to="all", reply="required")
    assert env.is_addressed_to("aerial") is True
    assert env.should_reply("aerial") is True

def test_envelope_parse_list_to():
    text = (
        "```handoff\n"
        "{\n"
        '  "v": 1,\n'
        '  "kind": "handoff",\n'
        '  "reply": "required",\n'
        '  "floor": "open",\n'
        '  "subject": "agora-audit",\n'
        '  "to": ["amos", "aerial"]\n'
        "}\n"
        "```"
    )
    parsed = parse_envelope(text)
    assert parsed is not None
    assert parsed.to == ["amos", "aerial"]
    assert parsed.is_addressed_to("aerial") is True
    assert parsed.is_addressed_to("amos") is True
    assert parsed.is_addressed_to("zero") is False
