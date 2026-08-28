from omnibot import trace


def test_trace_event_has_action_status_and_timestamp(monkeypatch):
    monkeypatch.setattr(trace.time, "time", lambda: 123.0)
    event = trace.trace_event("click", {"selector": "@e1"}, {"status": "success"})
    assert event["action"] == "click"
    assert event["timestamp"] == 123.0
    assert event["result"]["status"] == "success"


def test_replay_payload_requires_actions_list():
    assert trace.parse_replay_payload({"actions": [{"action": "snapshot", "params": {}}]})[0]["action"] == "snapshot"


def test_replay_payload_rejects_missing_actions():
    try:
        trace.parse_replay_payload({})
    except ValueError as exc:
        assert "actions list" in str(exc)
    else:
        raise AssertionError("parse_replay_payload should reject missing actions")
