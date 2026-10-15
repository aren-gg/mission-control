"""Contract tests for roster loading and mock/Codex event sources."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from adapter import create_source, load_config, load_roster
from sources import CodexAppServerSource, MockEventSource, make_event


def agent(agent_id: str, *, thread_id: str | None = None) -> dict:
    return {
        "id": agent_id,
        "name": agent_id.title(),
        "role": f"Does {agent_id} work",
        "model": "gpt-6.1-sol",
        "species": "beluga",
        "accent_color": "#DDEBF0",
        "app_server_thread_id": thread_id,
    }


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


def test_load_roster_checks_unique_ids_and_supported_palette(tmp_path):
    path = tmp_path / "agents.json"
    write_json(path, [agent("backend")])
    assert load_roster(path) == [agent("backend")]

    write_json(path, [agent("backend"), agent("backend")])
    with pytest.raises(ValueError, match="duplicate id"):
        load_roster(path)

    write_json(path, [{**agent("backend"), "accent_color": "#123456"}])
    with pytest.raises(ValueError, match="shared palette"):
        load_roster(path)

    write_json(path, [{**agent("bad id")}])
    with pytest.raises(ValueError, match="id"):
        load_roster(path)


def test_invalid_config_safely_selects_mock(tmp_path):
    config = tmp_path / "config.json"
    write_json(tmp_path / "agents.json", [agent("backend")])
    config.write_text('{"source":"unknown"}', encoding="utf-8")
    loaded = load_config(config)
    assert loaded["source"] == "mock"
    assert loaded["warning"]
    source = create_source(tmp_path)
    try:
        assert isinstance(source, MockEventSource)
        assert source.config_warning
    finally:
        source.close()


def test_factory_defaults_to_mock_and_does_not_start_codex(tmp_path):
    write_json(tmp_path / "agents.json", [agent("backend")])
    write_json(tmp_path / "config.json", {"source": "mock"})

    source = create_source(tmp_path)
    try:
        assert isinstance(source, MockEventSource)
        assert source.mode == "mock"
        assert not source._started
    finally:
        source.close()


def test_mock_events_are_subscribed_and_history_replays_chronologically():
    source = MockEventSource([agent("backend"), agent("frontend")], interval=60)
    events = []
    source.subscribe(events.append)
    first = make_event("backend", "status_change", status="working", summary="Starting")
    second = make_event("backend", "tool_call", tool="shell", name="Run command", summary="Checking")
    other = make_event("frontend", "status_change", status="idle", summary="Other agent")
    try:
        source._publish(first)
        source._publish(other)
        source._publish(second)
        assert events == [first, other, second]
        assert source.get_history("backend") == [first, second]
        assert source.get_history("frontend") == [other]
    finally:
        source.close()


def test_history_keeps_at_least_500_newest_events():
    source = MockEventSource([agent("backend")], interval=60)
    try:
        for index in range(1005):
            source._publish(make_event("backend", "status_change", status="working", summary=f"Event {index}"))
        history = source.get_history("backend")
        assert len(history) == 1000
        assert history[0]["data"]["summary"] == "Event 5"
        assert history[-1]["data"]["summary"] == "Event 1004"
    finally:
        source.close()


def test_mock_source_rejects_blank_and_unknown_agent_messages():
    source = MockEventSource([agent("backend")], interval=60)
    try:
        with pytest.raises(ValueError, match="blank"):
            source.send_message("backend", "  ")
        with pytest.raises(ValueError, match="Unknown agent"):
            source.send_message("missing", "Hello")
    finally:
        source.close()


def test_mock_message_routes_to_only_the_addressed_agent():
    source = MockEventSource([agent("backend"), agent("frontend")], interval=60)
    events = []
    source.subscribe(events.append)
    try:
        source.start()
        assert wait_until(lambda: len(events) >= 2)
        events.clear()

        message_id = source.send_message("frontend", "Please inspect the form")

        assert wait_until(lambda: any(e["type"] == "message" and e["data"].get("role") == "assistant" for e in events))
        routed = [e for e in events if e.get("agent_id") == "frontend"]
        assert any(e["type"] == "message" and e["data"].get("role") == "user" and e["data"].get("message_id") == message_id for e in routed)
        assert any(e["type"] == "message" and e["data"].get("role") == "assistant" for e in routed)
        assert all(e.get("agent_id") == "frontend" for e in events)
        assert source.get_history("frontend")[-1]["agent_id"] == "frontend"
    finally:
        source.close()


FAKE_APP_SERVER = r'''import json, sys
log_path = sys.argv[1]
for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if not method:
        continue
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(method + "\n")
    if method == "initialize":
        result = {"capabilities": {}}
    elif method == "thread/start":
        result = {"thread": {"id": "created-thread-1", "turns": []}}
    elif method == "thread/resume":
        result = {"thread": {"id": request["params"]["threadId"], "turns": []}}
    elif method == "thread/turns/list":
        result = {"data": [{"createdAt": "2026-10-15T12:00:00Z", "items": [
            {"id": "history-user-1", "type": "userMessage", "content": [{"type": "text", "text": "Earlier Codex question"}]},
            {"id": "history-message-1", "type": "agentMessage", "text": "Earlier Codex result"}
        ]}], "nextCursor": None}
    elif method == "turn/start":
        thread_id = request["params"]["threadId"]
        print(json.dumps({"method": "turn/started", "params": {"threadId": thread_id}}), flush=True)
        print(json.dumps({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "itemId": "reply-message-1", "delta": "Fake Codex reply"}}), flush=True)
        print(json.dumps({"method": "item/completed", "params": {"threadId": thread_id, "item": {"id": "reply-message-1", "type": "agentMessage", "text": "Fake Codex reply"}}}), flush=True)
        print(json.dumps({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"status": "completed"}}}), flush=True)
        result = {"turn": {"id": "turn-1"}}
    else:
        result = {}
    if "id" in request:
        print(json.dumps({"id": request["id"], "result": result}), flush=True)
'''


def test_codex_fake_app_server_creates_persists_replays_and_routes_message(tmp_path):
    roster_path = tmp_path / "agents.json"
    write_json(roster_path, [agent("backend")])
    fake_path = tmp_path / "fake_app_server.py"
    log_path = tmp_path / "fake-requests.jsonl"
    fake_path.write_text(FAKE_APP_SERVER, encoding="utf-8")
    source = CodexAppServerSource(
        load_roster(roster_path),
        command=[sys.executable, str(fake_path), str(log_path)],
        project_root=tmp_path,
        roster_path=roster_path,
        reconnect_delay=0.05,
        request_timeout=2,
    )
    events = []
    source.subscribe(events.append)
    try:
        source.start()
        assert wait_until(lambda: bool(source._ready))
        assert wait_until(lambda: json.loads(roster_path.read_text(encoding="utf-8"))[0].get("app_server_thread_id") == "created-thread-1")
        replay = source.get_history("backend")
        assert [(e["data"].get("role"), e["data"].get("content")) for e in replay if e["type"] == "message"] == [
            ("user", "Earlier Codex question"), ("assistant", "Earlier Codex result")]

        source.send_message("backend", "Check the current change")
        assert wait_until(lambda: any(e["type"] == "message" and e["data"].get("content") == "Fake Codex reply" for e in events))

        history = source.get_history("backend")
        user = next(e for e in history if e["type"] == "message" and e["data"].get("role") == "user" and e["data"].get("content") == "Check the current change")
        replies = [e for e in history if e["type"] == "message" and e["data"].get("content") == "Fake Codex reply"]
        assert user["data"]["content"] == "Check the current change"
        assert len(replies) == 1  # delta + completed item update one message, not two
        assert all(e["agent_id"] == "backend" for e in history)
        methods = [e["data"].get("status") for e in history if e["type"] == "status_change"]
        assert "working" in methods
        assert "idle" in methods
        request_methods = log_path.read_text(encoding="utf-8").splitlines()
        assert "thread/start" in request_methods
        assert "thread/turns/list" in request_methods
        assert "turn/start" in request_methods
    finally:
        source.close()


def test_codex_fake_app_server_resumes_configured_thread(tmp_path):
    roster_path = tmp_path / "agents.json"
    write_json(roster_path, [agent("backend", thread_id="existing-thread-7")])
    fake_path = tmp_path / "fake_app_server.py"
    log_path = tmp_path / "fake-requests.jsonl"
    fake_path.write_text(FAKE_APP_SERVER, encoding="utf-8")
    source = CodexAppServerSource(
        load_roster(roster_path),
        command=[sys.executable, str(fake_path), str(log_path)],
        project_root=tmp_path,
        roster_path=roster_path,
        reconnect_delay=0.05,
        request_timeout=2,
    )
    try:
        source.start()
        assert wait_until(lambda: bool(source._ready))
        assert wait_until(lambda: log_path.exists() and "thread/turns/list" in log_path.read_text(encoding="utf-8"))
        methods = log_path.read_text(encoding="utf-8").splitlines()
        assert "thread/resume" in methods
        assert "thread/start" not in methods
        assert load_roster(roster_path)[0]["app_server_thread_id"] == "existing-thread-7"
    finally:
        source.close()


def test_config_codex_factory_selects_codex_mode(tmp_path):
    write_json(tmp_path / "agents.json", [agent("backend")])
    write_json(tmp_path / "config.json", {"source": "codex", "app_server_command": [sys.executable, "fake-server.py"]})

    source = create_source(tmp_path)
    try:
        assert isinstance(source, CodexAppServerSource)
        assert source.mode == "codex"
        assert source.command == [sys.executable, "fake-server.py"]
        assert not source._started
    finally:
        source.close()

