# Mission Control Contract

This contract is the shared source of truth for the desktop app, event sources, tests, and documentation. The Orchestrator coordinates and reviews; it does not implement feature code. Each agent edits only its assigned files.

## Architecture and ownership

- `python main.py` opens a PySide6 desktop application. There is no FastAPI server, WebSocket, or browser front end.
- Qt widgets consume the `AgentEventSource` interface directly. Implementations emit typed events; the UI adapts them onto Qt signals/slots before updating widgets.
- Backend owns `adapter.py`, `workspace.py`, `sources/`, `agents.json`, `config.json`, `workspace.json`, `data/`, `.gitignore`, `requirements.txt`, `run.command`, and `run.bat`.
- Front End owns `main.py`, `ui/`, `sprites.py`, and `assets/` (font only).
- Mission Control owns `tests/` and `README.md`; it reports defects to the Orchestrator and does not repair other owners' files.
- The Orchestrator owns `CONTRACT.md`, coordinates integration, and routes bugs to the owner.

## Roster and settings

`agents.json` is an array of 1–8 objects with stable unique lowercase IDs. Fields:

```json
{
  "id": "orchestrator",
  "name": "Orchestrator",
  "role": "Coordinates implementation work",
  "model": "gpt-6-astra",
  "species": "blue_whale",
  "accent_color": "#5BC0BE",
  "app_server_thread_id": null
}
```

`app_server_thread_id` is an optional thread ID. In Codex mode, resume a configured thread; if absent, create a thread for that agent with its configured model and role instructions, then persist the returned ID into `agents.json` for future runs. If thread creation or connection fails for one agent, only that agent falls back to mock activity and its tab must be marked `DEMO` with a visible error. The four default agents are Orchestrator (gpt-6-astra, blue whale), Front End (gpt-6.1-sol, beluga), Back End (gpt-6.1-sol, orca), and Mission Control (gpt-6-luna, sperm whale). Keep each agent's role text and model visible in its tab.

`config.json` has `{"source":"mock"}` by default; no Codex thread is started unless the user switches the setting to `codex`. Supported values are `mock` and `codex`. Invalid values fail clearly and safely to mock mode. The Codex source must never label mock-generated activity as live.

## Event contract

Every event is a mapping with `type`, `agent_id`, UTC ISO-8601 `timestamp`, and `data`:

```json
{"type":"status_change","agent_id":"backend","timestamp":"2026-10-15T14:05:00Z","data":{"status":"working","summary":"Reading adapter"}}
```

Event types:

- `status_change`: `status` is `idle|working|thinking|tool_call|waiting|error`; `summary` is short text.
- `message`: `message_id`, `role` (`user|assistant`), and full `content`.
- `tool_call`: `tool`, `name`, and `summary`.
- `error`: `message` and optional diagnostic `detail`.

`AgentEventSource` exposes the roster, per-agent chronological history, an event subscription callback, `send_message(agent_id, content)`, and `close()`. Retain at least the newest 500 events per agent, including user/assistant messages. Blank messages are rejected. User input always routes only to the selected agent. A Codex adapter sends to that agent's thread and maps app-server notifications into these events. If creating/resuming one agent's Codex thread fails, only that agent uses mock activity and is labeled `DEMO`.

The Codex implementation uses the documented app-server JSON-RPC protocol. For local integration, launch `codex app-server` with stdio JSONL or connect to an explicitly configured local Unix/WebSocket endpoint; initialize before requests. Thread IDs are explicit roster configuration. Map thread/turn/item lifecycle, assistant text, tool starts/results, and errors to the event contract; preserve source timestamps when available and otherwise use UTC receipt time. Reconnect with bounded exponential backoff and surface connection errors in the affected live agents' logs. Do not silently replace a configured live agent with mock data. The app-server is experimental; do not expose an unauthenticated non-local listener.

## Desktop interface

### Project and team management (current revision)

- Provide an in-app project selector, Add project folder picker, Open project folder action, and a source selector labeled Demo activity / Codex agents. Display the selected project name and absolute working folder. Users do not need to edit JSON to perform these operations.
- Every project has its own independent roster, instruction files, source mode, and thread IDs. Adding a project copies a reusable team preset, with no copied thread IDs. Switching projects closes the previous source before starting the new one, ignores stale callbacks, and uses the selected folder as the Codex working directory. Files in other selected project directories are not modified by the configuration editor; its state and instructions stay in this app's managed `data/` directory.
- Provide an agent editor with Add, Edit, Remove (retain 1-8 agents), display name, role, editable model selection, reasoning effort, linked teammates, and a readable multiline instruction editor. Show the instruction file path, open it in the user's editor, and support reloading external edits. Stable agent IDs must not change on rename. Save validates input and displays actionable errors.
- Agent message composers include a Reference files picker rooted in the selected project. It inserts selected relative file paths into the draft without sending it; only files inside that project are accepted. Explain that these are project file references rather than uploaded attachments.
- Save the current team as a named reusable preset, optionally the default for new projects, and apply a preset to a project through a clearly confirmed replace operation. Presets contain configuration and instruction text, never thread IDs or other project's paths. Editing a copied team must not modify its preset or another project.
- Changing model, reasoning effort, role instructions, or external instruction file contents invalidates that agent's current thread mapping and starts a new conversation on the next Codex connection. Existing Codex conversations are retained by Codex. Cosmetic edits preserve the thread mapping. The editor explains this behavior.
- Existing `agents.json`, `config.json`, and `.codex/agents/*.toml` are imported on first startup to preserve the user's initial setup. `workspace.json` and project rosters thereafter hold managed state; legacy files remain available as import defaults.

### WorkspaceStore integration API

`workspace.WorkspaceStore(app_root=None)` is the synchronous persistence boundary (no Qt dependency):

- `.projects` and `.presets`: lists of project/preset dictionaries; projects include `id`, `name`, `path`, `source`; presets include `id`, `name`. `.active_project` and `.default_preset_id` expose current choices.
- `.select_project(project_id)`; `.add_project(name, path, preset_id=None)` returns a new project dictionary without selecting it; `.set_source(mode, project_id=None)` persists mock/codex.
- `.list_agents(project_id=None)`, `.read_instructions(agent_id, project_id=None)`, `.instructions_path(agent_id, project_id=None)`.
- `.save_agent(agent, instructions, project_id=None)` validates and persists the agent; a missing ID generates a unique stable ID. `.remove_agent(agent_id, project_id=None)` retains at least one agent.
- `.save_preset(name, project_id=None, make_default=False)` returns its dictionary; `.apply_preset(preset_id, project_id=None)` replaces the current project's team only; `.reset_thread(agent_id, project_id=None)` starts a fresh conversation without deleting existing Codex records.
- `.create_source(project_id=None)` returns the agreed `AgentEventSource`, with the selected project as Codex cwd, project-specific roster persistence, and saved instructions and reasoning effort loaded for every custom agent. All `project_id=None` arguments refer to the active project. Use atomic state writes and protect the app's managed instruction paths from traversal.

### Professional workspace and guided setup (current revision)

This revision replaces the pixel Office presentation. Use a professional, minimal desktop workspace with a neutral palette, restrained accent colors, readable system text, clear navigation, and generous spacing. Do not render the aquarium, whale sprites, pixel text, or decorative animation in the active UI. Legacy species/color configuration remains compatible but is not required for normal setup.

- Team overview shows each configured agent, role, live connection/status, linked teammates, and direct access to its conversation. Individual conversations remain independent and addressed explicitly.
- Keep project selection, Add project, Manage team, and source selection easy to find. Show selected working folder and distinguish Demo, Connecting, Live, and errors truthfully.
- A separate, always-accessible Setup Guide walks through project selection, Codex CLI installation/sign-in, connection, adding/removing agents, model/effort/instructions, links and handoffs, separate chats, JSON editing/reloading, and reusable team presets. Include Back/Next navigation and actions opening relevant app controls. Show actual selected-project paths; do not claim authentication or connection based only on a checked tutorial step.
- Team editor exposes linked teammates and an explicit optional existing Codex thread attachment. Existing thread attachment must be distinct from editing a model or role. Thread identifiers are unique across this workspace to prevent accidentally sharing a conversation.
- Advanced JSON controls open the active project's actual roster file and reload validated edits with actionable errors. Preserve unsaved editor safeguards. Explain stable IDs, instruction paths, behavior changes that start new conversations, and keeping a backup before manual edits.
- Each agent conversation includes a handoff action selecting a linked teammate and a message. Sending ordinary chat addresses that agent only. A handoff explicitly starts work on its target and records its origin.
- Screenshot mode captures overview, each agent chat, team settings, and tutorial; retain offscreen support. Verify desktop layouts at ordinary screen sizes, including long names and Unicode.

### Linked-agent integration

- Roster field `linked_agent_ids` is a list of directed delegation targets within the same project. Reject unknown IDs, duplicates, and self-links. Removing an agent cleans incoming links. Presets copy links without sharing conversations or paths.
- `WorkspaceStore.roster_path(project_id=None)` returns the selected managed roster path; `reload_project_config(project_id=None)` validates edited configuration before derived writes; `link_existing_thread(agent_id, thread_id, project_id=None)` attaches an explicitly supplied existing conversation. Behavior edits invalidate attached mappings just like created mappings.
- `AgentEventSource.delegate_message(from_agent_id, to_agent_id, content)` returns a `concurrent.futures.Future[str]`, checks the configured link, routes work to the actual target, and records provenance in both histories. Demo activity stays labeled as simulation.
- Codex agents can delegate to configured teammates through an app-provided dynamic tool. Tool execution must use separate target threads and deliver target completion results to the caller, without blocking the JSON-RPC reader. Busy targets, cycles, timeout, source closure, and errors must resolve clearly without fabricating results. Use the documented experimental API opt-in. An unsupported server must surface the limitation. The installed app-server accepts dynamic tools on thread creation only. Persist a tool-version marker for app-created threads; old/externally attached conversations without that marker support direct chat and manual handoffs, but show a clear automatic-delegation limitation with a New conversation remedy. Never send an unsupported dynamicTools override on resume.
- Linking configured agents is app-managed routing, distinct from discovering arbitrary Codex native child agents. Keep this distinction accurate in UI/docs. Existing thread attachment is explicit; do not silently map unrelated native subagents to the visible roster.
- Preserve project isolation, stale-source callback rejection, per-agent model/effort/instructions, and independent user conversations. Tests use fake app-server events, never real model calls unless explicitly requested.

## Launchers and verification

- `run.command` is executable on macOS; on double-click it creates a project virtual environment if missing, installs `requirements.txt`, then starts the app.
- `run.bat` performs equivalent setup and launch on Windows.
- Mission Control verifies roster loading, event routing, message routing, history replay, Codex source using a fake app-server, and both launchers where available. It runs screenshot mode and visually checks the overview, conversations, settings, and guide for clarity and clipping. Report any failure to the Orchestrator as `[owner] / [file] / [problem] / [reproduction]`.
- README gives beginner-level launch instructions, guided setup, agent editing, teammate links, handoffs, JSON editing/reloading, instructions, reusable presets, and switching between Demo and Codex sources. Document older-thread automatic delegation and unsupported interactive approval limitations.
