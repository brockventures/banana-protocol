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


def test_recipient_match_is_exact_not_substring():
    env = HandoffEnvelope(to=["amos-dashboard"], reply="required")
    assert env.is_addressed_to("amos-dashboard") is True
    assert env.is_addressed_to("amos") is False
    assert HandoffEnvelope(to="zeroth", reply="required").is_addressed_to("zero") is False


def test_recipient_normalisation():
    env = HandoffEnvelope(to=["@Amos", None, 7], target="aerial", reply="required")
    assert env.is_addressed_to("amos") is True
    assert env.is_addressed_to("aerial") is True
    assert env.is_addressed_to("no") is False
    assert env.is_addressed_to("none") is False


def test_legacy_comma_string_and_star_wildcard():
    env = HandoffEnvelope(to="amos, aerial", reply="required")
    assert env.is_addressed_to("aerial") is True
    assert env.is_addressed_to("zero") is False
    assert HandoffEnvelope(target=["*"], reply="required").is_addressed_to("zero") is True


def test_envelope_version_is_1_1():
    assert HandoffEnvelope().v == 1.1
    assert '"v": 1.1' in format_envelope(kind="status", reply="none", subject="v-check")
