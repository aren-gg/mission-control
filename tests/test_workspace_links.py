"""Workspace linked-agent, thread-attachment and raw-JSON reload tests."""
from __future__ import annotations

import json

import pytest

from workspace import WorkspaceStore


def project_pair(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    store = WorkspaceStore(app)
    first_path, second_path = tmp_path / "first", tmp_path / "second"
    first_path.mkdir()
    second_path.mkdir()
    first = store.add_project("First", first_path)
    second = store.add_project("Second", second_path)
    return app, store, first, second


def test_linked_ids_validate_remove_cleaning_preset_copy_and_project_isolation(tmp_path):
    _app, store, first, second = project_pair(tmp_path)
    first_team = store.list_agents(first["id"])
    caller, target = first_team[0], first_team[1]
    linked = store.save_agent(
        {**caller, "linked_agent_ids": [target["id"]]},
        store.read_instructions(caller["id"], first["id"]),
        first["id"],
    )
    assert linked["linked_agent_ids"] == [target["id"]]

    with pytest.raises(ValueError, match="unknown|Unknown"):
        store.save_agent({**linked, "linked_agent_ids": ["missing"]}, "", first["id"])
    with pytest.raises(ValueError, match="duplicate|Duplicate"):
        store.save_agent({**linked, "linked_agent_ids": [target["id"], target["id"]]}, "", first["id"])
    with pytest.raises(ValueError, match="self|Self"):
        store.save_agent({**linked, "linked_agent_ids": [caller["id"]]}, "", first["id"])

    preset = store.save_preset("Linked team", first["id"])
    assert preset["agents"][0]["linked_agent_ids"] == [target["id"]]
    store.apply_preset(preset["id"], second["id"])
    second_caller = store.list_agents(second["id"])[0]
    assert second_caller["linked_agent_ids"] == [target["id"]]
    assert second_caller["app_server_thread_id"] is None

    # Editing the copied project's routing cannot mutate the original roster or preset.
    store.save_agent(
        {**second_caller, "linked_agent_ids": []},
        store.read_instructions(second_caller["id"], second["id"]),
        second["id"],
    )
    assert store.list_agents(first["id"])[0]["linked_agent_ids"] == [target["id"]]
    assert preset["agents"][0]["linked_agent_ids"] == [target["id"]]

    store.remove_agent(target["id"], first["id"])
    assert all(target["id"] not in a["linked_agent_ids"] for a in store.list_agents(first["id"]))


def test_existing_thread_attachment_is_explicit_workspace_unique_and_isolated(tmp_path):
    _app, store, first, second = project_pair(tmp_path)
    first_team = store.list_agents(first["id"])
    chosen = first_team[1]
    before = {key: chosen.get(key) for key in ("id", "model", "role", "reasoning_effort")}

    attached = store.link_existing_thread(chosen["id"], "codex-thread-existing-1", first["id"])
    assert attached["app_server_thread_id"] == "codex-thread-existing-1"
    assert {key: attached.get(key) for key in before} == before
    assert store.list_agents(second["id"])[1]["app_server_thread_id"] is None
    with pytest.raises(ValueError, match="already|unique|attached"):
        store.link_existing_thread(store.list_agents(second["id"])[1]["id"], "codex-thread-existing-1", second["id"])
    assert store.list_agents(first["id"])[1]["app_server_thread_id"] == "codex-thread-existing-1"
    assert store.list_agents(second["id"])[1]["app_server_thread_id"] is None


def test_link_changes_invalidate_thread_mapping_and_reject_stale_saver(tmp_path):
    app, store, first, _second = project_pair(tmp_path)
    team = store.list_agents(first["id"])
    caller, target = team[0], team[1]
    roster_path = store.roster_path(first["id"])
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster[0]["app_server_thread_id"] = "old-caller-thread"
    roster_path.write_text(json.dumps(roster), encoding="utf-8")
    snapshot = store.list_agents(first["id"])[0]

    changed = store.save_agent(
        {**snapshot, "linked_agent_ids": [target["id"]]},
        store.read_instructions(caller["id"], first["id"]),
        first["id"],
    )
    assert changed["app_server_thread_id"] is None
    with pytest.raises(ValueError, match="stale|changed"):
        store._save_thread(first["id"], snapshot, "late-old-thread-response")
    assert store.list_agents(first["id"])[0]["app_server_thread_id"] is None


def test_reload_project_config_validates_before_derived_writes(tmp_path):
    _app, store, first, _second = project_pair(tmp_path)
    caller, target = store.list_agents(first["id"])[:2]
    store.link_existing_thread(caller["id"], "reload-thread-id", first["id"])
    path = store.roster_path(first["id"])
    before = json.loads(path.read_text(encoding="utf-8"))
    caller_row = next(row for row in before if row["id"] == caller["id"])
    caller_row["linked_agent_ids"] = ["unknown-target"]
    path.write_text(json.dumps(before), encoding="utf-8")
    store.instructions_path(caller["id"], first["id"]).write_text("edited out of band", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown|Unknown"):
        store.reload_project_config(first["id"])
    after = json.loads(path.read_text(encoding="utf-8"))
    persisted = next(row for row in after if row["id"] == caller["id"])
    original = next(row for row in before if row["id"] == caller["id"])
    # Failed reload may not partially update a fingerprint or clear the old mapping.
    assert persisted.get("behavior_fingerprint") == original.get("behavior_fingerprint")
    assert persisted.get("app_server_thread_id") == "reload-thread-id"

    caller_row["linked_agent_ids"] = [target["id"]]
    caller_row["model"] = "gpt-6-sol"
    path.write_text(json.dumps(before), encoding="utf-8")
    reloaded = store.reload_project_config(first["id"])
    saved = next(row for row in reloaded if row["id"] == caller["id"])
    assert saved["model"] == "gpt-6-sol"
    assert saved["linked_agent_ids"] == [target["id"]]
    assert saved["app_server_thread_id"] is None

