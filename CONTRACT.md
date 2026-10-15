# Underwater Agent Office Contract

This contract is the shared source of truth for the desktop app, event sources, tests, and documentation. The Orchestrator coordinates and reviews; it does not implement feature code. Each agent edits only its assigned files.

## Architecture and ownership

- `python main.py` opens a PySide6 desktop application. There is no FastAPI server, WebSocket, or browser front end.
- Qt widgets consume the `AgentEventSource` interface directly. Implementations emit typed events; the UI adapts them onto Qt signals/slots before updating widgets.
- Backend owns `adapter.py`, `sources/`, `agents.json`, `config.json`, `requirements.txt`, `run.command`, and `run.bat`.
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

- Main window uses a tab bar containing `Office` plus one tab per current roster entry.
- Office scene is custom-painted with `QPainter`, uses logical resolution 480×270, integer scaling, nearest-neighbor rendering, and no smoothing/antialiasing.
- Clicking a whale opens its agent tab. Tabs remain keyboard-operable.
- Each agent tab has a whale sprite and header with name, role, model, live status and, where applicable, `DEMO` tag; a scrolling timestamped activity/chat log; and a message input. Style user messages, agent messages, tool calls, and errors distinctly. On new events, scroll only if already near the bottom.
- Support `QT_QPA_PLATFORM=offscreen python main.py --screenshot out.png` to save the Office view and each agent tab as separate PNGs (use a deterministic filename suffix for each tab).

## Pixel art

Use only this 16-color palette in all UI and art:

| Name | Hex |
|---|---|
| deep ink | `#0B132B` |
| midnight | `#1C2541` |
| slate blue | `#3A506B` |
| sea teal | `#5BC0BE` |
| bright aqua | `#6FFFE9` |
| warm paper | `#F4F1DE` |
| sand | `#F2CC8F` |
| coral | `#E07A5F` |
| warning red | `#BC4749` |
| kelp | `#386641` |
| leaf | `#6A994E` |
| lime | `#A7C957` |
| wood | `#8D6E63` |
| soft gray | `#A0AEC0` |
| ice | `#DDEBF0` |
| white | `#FFFFFF` |

Draw art in code with flat fills, crisp 1px dark outlines, and 2–3 shades per object. No image assets, gradients, blur, or smoothing. Whales are 48×24 to 64×32 logical pixels, side-on with rounded body, tail flukes, pectoral flipper, and eye. They gently bob and animate their tail, float beside or above desks, and swim between locations; never walk or rest on furniture. Species silhouettes must be distinct: blue whale is long/slender, mottled blue-gray, small dorsal fin and pale belly grooves; beluga is light, bulbous-foreheaded and has no dorsal fin; orca is black/white with eye patch and tall dorsal fin; sperm whale has a blocky head about one-third of body length, dark teal-gray coloring, and 1–2 darker wrinkle lines. Small bubbles rise from every whale; idle surface pose may show a blowhole spout.

Animation states: `idle`, `working`, `tool`, `error`, `walking`. Derive from event status; thinking/waiting may use idle/tool pose while retaining actual status text. Tool/file activity moves whales toward a cabinet; shell activity toward a terminal. Orchestrator delegation shows travel and clipboard handoff. Error shows a red `!`; Mission Control warning light flashes while any current agent errors.

Speech bubbles anchor over each whale's head with a small pointer, show at most 36 characters (truncate with `...`), and use collision avoidance/staggering so they never overlap. Name labels are fully visible below desks. Use ASCII-only UI text (no em dash or unsupported glyph); bundle or draw a pixel font that supports every displayed character. Leave layout margins so all status text is visible and never clipped.

## Launchers and verification

- `run.command` is executable on macOS; on double-click it creates a project virtual environment if missing, installs `requirements.txt`, then starts the app.
- `run.bat` performs equivalent setup and launch on Windows.
- Mission Control verifies roster loading, event routing, message routing, history replay, Codex source using a fake app-server, and both launchers where available. It runs screenshot mode and visually checks every art/text requirement. Report any failure to the Orchestrator as `[owner] / [file] / [problem] / [reproduction]`.
- README gives beginner-level double-click instructions, roster editing, and switching between mock and Codex sources.
