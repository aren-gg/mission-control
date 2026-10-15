"""Workspace persistence contract tests (no real Codex/model calls)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from workspace import WorkspaceStore


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


FAKE_SERVER = r'''import json, os, sys
log = sys.argv[1]
with open(log, "a", encoding="utf-8") as stream:
    stream.write(os.getcwd() + chr(10))
thread_number = 0
for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if not method:
        continue
    if method == "initialize":
        result = {"capabilities": {}}
    elif method == "thread/start":
        thread_number += 1
        result = {"thread": {"id": "thread-for-" + os.path.basename(os.getcwd()) + "-" + str(thread_number), "turns": []}}
    elif method == "thread/resume":
        result = {"thread": {"id": request["params"]["threadId"], "turns": []}}
    elif method == "thread/turns/list":
        result = {"data": [], "nextCursor": None}
    else:
        result = {}
    if "id" in request:
        print(json.dumps({"id": request["id"], "result": result}), flush=True)
'''


def ready(source):
    source.start()
    assert wait_until(lambda: bool(source._ready)), "fake app-server did not initialize"


def test_project_teams_and_instructions_are_isolated(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    store = WorkspaceStore(app)
    first_root, second_root = tmp_path / "first", tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = store.add_project("First", first_root)
    second = store.add_project("Second", second_root)

    first_agent = store.list_agents(first["id"])[0]
    second_agent = next(a for a in store.list_agents(second["id"]) if a["id"] == first_agent["id"])
    store.save_agent({**first_agent, "role": "First project only"}, "instructions for first", first["id"])
    store.save_agent({**second_agent, "role": "Second project only"}, "instructions for second", second["id"])

    assert store.read_instructions(first_agent["id"], first["id"]) == "instructions for first"
    assert store.read_instructions(first_agent["id"], second["id"]) == "instructions for second"
    assert store.list_agents(first["id"])[0]["role"] == "First project only"
    assert store.list_agents(second["id"])[0]["role"] == "Second project only"
    assert store.instructions_path(first_agent["id"], first["id"]) != store.instructions_path(first_agent["id"], second["id"])


def test_preset_is_a_detached_copy_without_thread_ids_or_paths(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    store = WorkspaceStore(app)
    a_path, b_path = tmp_path / "alpha", tmp_path / "beta"
    a_path.mkdir(); b_path.mkdir()
    alpha = store.add_project("Alpha", a_path)
    beta = store.add_project("Beta", b_path)

    agent = store.list_agents(alpha["id"])[0]
    # Simulate a saved thread mapping from an earlier Codex session.
    roster_path = app / "data" / "projects" / alpha["id"] / "agents.json"
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster[0]["app_server_thread_id"] = "alpha-thread"
    write_json(roster_path, roster)
    store.save_agent({**agent, "name": "Alpha renamed"}, store.read_instructions(agent["id"], alpha["id"]), alpha["id"])
    preset = store.save_preset("Alpha team", alpha["id"])

    assert "app_server_thread_id" not in preset["agents"][0]
    assert "instructions_file" not in preset["agents"][0]
    store.apply_preset(preset["id"], beta["id"])
    copied = store.list_agents(beta["id"])[0]
    assert copied["app_server_thread_id"] is None
    assert copied["instructions_file"] == f"instructions/{copied['id']}.md"
    assert store.read_instructions(copied["id"], beta["id"]) == store.read_instructions(agent["id"], alpha["id"])

    store.save_agent({**copied, "name": "Beta only"}, "changed in beta", beta["id"])
    assert store.list_agents(alpha["id"])[0]["name"] == "Alpha renamed"
    assert preset["agents"][0]["name"] != "Beta only"


def test_applying_same_behavior_preset_rejects_stale_thread_mapping(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    store = WorkspaceStore(app)
    project_id = store.active_project["id"]
    snapshot = store.list_agents(project_id)[0]
    preset = store.save_preset("same team", project_id)

    # Applying a preset is a deliberate new-conversation boundary, even when
    # the agent behavior text happens to be identical to the current team.
    store.apply_preset(preset["id"], project_id)
    with pytest.raises(ValueError, match="stale thread mapping"):
        store._save_thread(project_id, snapshot, "late-response-from-old-source")


def test_behavior_edits_and_external_instruction_edits_invalidate_thread(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    store = WorkspaceStore(app)
    project_id = store.active_project["id"]
    original = store.list_agents(project_id)[0]
    path = app / "data" / "projects" / project_id / "agents.json"

    def set_thread(thread_id):
        roster = json.loads(path.read_text(encoding="utf-8"))
        row = next(a for a in roster if a["id"] == original["id"])
        row["app_server_thread_id"] = thread_id
        write_json(path, roster)

    set_thread("kept-for-cosmetic")
    current = store.list_agents(project_id)[0]
    store.save_agent({**current, "name": "A new display name", "species": "orca"}, store.read_instructions(current["id"], project_id), project_id)
    assert store.list_agents(project_id)[0]["app_server_thread_id"] == "kept-for-cosmetic"

    for field, value in (("model", "gpt-6.1-sol"), ("reasoning_effort", "high"), ("role", "New role")):
        set_thread("invalidate-" + field)
        current = store.list_agents(project_id)[0]
        store.save_agent({**current, field: value}, store.read_instructions(current["id"], project_id), project_id)
        assert store.list_agents(project_id)[0]["app_server_thread_id"] is None

    set_thread("invalidate-instructions")
    current = store.list_agents(project_id)[0]
    store.save_agent(current, "new managed instruction text", project_id)
    assert store.list_agents(project_id)[0]["app_server_thread_id"] is None

    set_thread("invalidate-external-edit")
    current = store.list_agents(project_id)[0]
    store.instructions_path(current["id"], project_id).write_text("changed in external editor", encoding="utf-8")
    assert store.list_agents(project_id)[0]["app_server_thread_id"] is None


def test_roster_save_validation_and_remove_floor(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    store = WorkspaceStore(app)
    project_id = store.active_project["id"]
    initial = store.list_agents(project_id)
    with pytest.raises(ValueError, match="nonempty text"):
        store.save_agent({**initial[0], "name": "  "}, "instructions", project_id)
    with pytest.raises(ValueError, match="reasoning effort"):
        store.save_agent({**initial[0], "reasoning_effort": "impossible"}, "instructions", project_id)
    with pytest.raises(ValueError, match="shared palette"):
        store.save_agent({**initial[0], "accent_color": "#010203"}, "instructions", project_id)

    store.remove_agent(initial[0]["id"], project_id)
    remaining = store.list_agents(project_id)
    assert len(remaining) == len(initial) - 1
    for row in remaining[:-1]:
        store.remove_agent(row["id"], project_id)
    last = store.list_agents(project_id)[0]
    with pytest.raises(ValueError, match="at least one"):
        store.remove_agent(last["id"], project_id)


def test_codex_source_uses_selected_project_cwd_and_persists_separate_threads(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    command_file = app / "fake_app_server.py"
    cwd_log = app / "server-cwds.log"
    command_file.write_text(FAKE_SERVER, encoding="utf-8")
    store = WorkspaceStore(app)
    store_config = app / "config.json"
    write_json(store_config, {"source": "codex", "app_server_command": [sys.executable, str(command_file), str(cwd_log)]})
    first_path, second_path = tmp_path / "project-one", tmp_path / "project-two"
    first_path.mkdir(); second_path.mkdir()
    one = store.add_project("One", first_path)
    two = store.add_project("Two", second_path)
    store.set_source("codex", one["id"])
    store.set_source("codex", two["id"])

    sources = [store.create_source(one["id"]), store.create_source(two["id"])]
    try:
        for source in sources:
            ready(source)
        assert wait_until(lambda: all(
            all(a.get("app_server_thread_id") for a in store.list_agents(project["id"]))
            for project in (one, two)
        ))
        recorded = cwd_log.read_text(encoding="utf-8").splitlines()
        assert str(first_path.resolve()) in recorded
        assert str(second_path.resolve()) in recorded
        for project in (one, two):
            roster = store.list_agents(project["id"])
            assert all(a["app_server_thread_id"] for a in roster)
        assert {a["app_server_thread_id"] for a in store.list_agents(one["id"])}.isdisjoint(
            {a["app_server_thread_id"] for a in store.list_agents(two["id"])}
        )
    finally:
        for source in sources:
            source.close()

