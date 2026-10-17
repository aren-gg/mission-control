# Mission Control

Mission Control is a local desktop workspace for coordinating independent Codex agent conversations across your projects. It is a PySide6 app, not a localhost website; the dashboard does not run in Chrome.

The default source is **Demo activity**, which is simulated and makes no model calls. Switch a project to **Codex agents** when you are ready to connect real Codex threads. Starting the app does not start implementation work by itself.

## Start the app

Install Python 3.11 or newer. The first launch needs an internet connection to install the app's Python dependencies.

### macOS

1. In Finder, open the Mission Control folder.
2. Double-click `run.command`.
3. If macOS blocks it, control-click the file, choose **Open**, and confirm. If it is not executable, open Terminal in the folder and run `chmod +x run.command` once.
4. Keep the Terminal window open while using the app; closing it stops the app.

### Windows

1. In File Explorer, open the Mission Control folder.
2. Double-click `run.bat`.
3. Keep the command window open while using the app; closing it stops the app.

For a manual start, create a Python 3.11+ environment, install `requirements.txt`, and run `python main.py` (on macOS, `python3 main.py`).

## Before connecting Codex agents

Install the [Codex CLI](https://learn.chatgpt.com/docs/codex/cli), open Terminal or Command Prompt, run `codex` once, and complete sign-in if prompted. Then open or restart Mission Control and select **Codex agents**. Access to the models selected for your agents depends on your account.

The app runs one project team at a time. Switching projects while agents are working asks you to confirm because reconnecting may interrupt their current work.

## First project: from setup to a task

1. Start in **Demo activity** to explore without model calls.
2. Choose **Add project...**, select an existing code folder, and give the project a name. The selected folder becomes Codex's working directory.
3. Select the project and check its displayed absolute working path. Each project keeps its roster, instructions, source choice, and thread IDs separate.
4. Open **Manage team...** to review the agents or add, remove, and configure them. Link only agents you want to be able to hand work to.
5. Select **Codex agents** and wait for the status panel to show **Live**. **Connecting**, **Demo**, and errors are distinct states; setup steps in the guide do not claim a login or connection succeeded.
6. Open **Setup Guide** for a guided walkthrough. Its buttons open the relevant app controls; it does not change your settings without your action.
7. Open an agent's conversation and use **Send message** with a specific task. For example, message the Orchestrator: “Inspect this project and list three useful implementation tasks. Do not edit files yet.” For focused work, message a specialist directly. If you want one agent to hand a task to a linked teammate, use **Hand off task** and choose that teammate.

Each visible agent has its own conversation. Ordinary **Send message** goes only to the selected agent. A handoff is an explicit task to a linked agent and records where the work came from. The dashboard does not automatically forward user messages among agents. A Codex agent may create native Codex subagents inside its own conversation; those native subagents are not automatically linked to dashboard agents or shown as separate dashboard conversations.

## Projects and working folders

Use the **Project** selector to switch projects. **Add project...** lets you select a folder; **Open folder** opens the selected project in Finder or File Explorer. Verify the displayed absolute path before connecting Codex.

Project configuration and instructions live under the app's managed `data/` folder, not in the selected code folder. Switching projects closes the prior event source and connects the selected project's source. The app uses the selected project's path as Codex's working directory.

## Team, links, and conversations

Open **Manage team...** to add, remove, or select an agent for editing. The roster supports 1 to 8 agents. Configure its stable ID, display name, role, model, reasoning effort, and instructions. Renaming an agent keeps its ID. Model, effort, role, or instruction changes start a new conversation on the next Codex connection; the prior Codex conversation is retained. Use **New conversation...** when you want a fresh Codex thread without changing those settings.

### Link teammates and hand off work

In the team editor, use **Linked teammates** to choose which agents this agent may hand work to. Links are directed: if Orchestrator links to Back End, that allows Orchestrator to hand off to Back End; it does not automatically create a reverse link. Links stay inside the project and cannot target the same agent, an unknown agent, or a duplicate entry.

In an agent conversation, **Hand off task** explicitly sends work to one of that agent's linked teammates. The target works in its own conversation, and the caller receives the completed result. Busy targets, delegation cycles, unavailable tools, or connection failures are reported as failures; the app does not invent a successful result. Support for agent-to-agent delegation requires the Codex app-server's documented experimental API. If the server does not support it, the app surfaces that limitation.

### Attach an existing Codex conversation

To link an already existing Codex conversation, enter its ID in **Existing conversation ID** and choose **Attach conversation...**. This explicitly attaches that conversation to the selected agent; it does not discover or map arbitrary Codex child agents. Thread IDs must be unique across the workspace so two agents or projects cannot accidentally share one conversation. Attaching a thread is separate from changing the agent's model or role. Existing or attached conversations support direct chat and manual handoffs. The automatic `delegate_to_agent` tool is registered only when Mission Control creates a new conversation; use **New conversation...** to enable it for an older conversation.

### Edit or reload the roster JSON

The team editor provides **Open team JSON** and **Reload team JSON** for advanced editing. Keep a backup before editing the file. Open the JSON for the active project's actual roster, make your changes, then use **Reload team JSON** to validate and apply them. Invalid JSON or roster settings produce an error without applying a partial edit. Reloading protects unsaved form changes; respond to the prompt before continuing.

Agent IDs are stable lowercase identifiers and are used by links. Keep IDs unique, preserve managed instruction paths, and make sure each `linked_agent_ids` entry names another agent in the same project. Configuration changes that affect behavior invalidate that agent's attached thread mapping and the next Codex connection starts a fresh conversation.

The editor shows the managed instruction file path for the selected agent. Choose **Open instruction file** to edit it in your normal editor, then **Reload external edits** in Manage team to bring saved changes into the form. You can also edit instructions directly in the multiline field and choose **Save agent**. Instruction changes start a new conversation the next time Codex connects.

To reuse a team, choose **Save team as preset...**, enter a name, and optionally make it the default for new projects. To copy a saved team into the current project, select it under **Team presets** and choose **Apply preset...**; confirm the replacement. Presets copy agent settings, links, and instruction text, but never conversation IDs or another project's paths. Later edits to this project do not change the preset.

## Guided setup

**Setup Guide** is available from the main workspace. Use its **Previous**/**Next** navigation to review project selection, Codex CLI setup, connection status, team editing, links and handoffs, separate conversations, JSON editing, and reusable presets. Guide actions open the corresponding controls. A visited step is only a tutorial step; it does not prove that Codex is signed in or connected.

## Demo, Live, and connection setup

- **Demo** means activity is simulated; it is not a live Codex thread.
- **Connecting** means the app is starting or resuming the agent's conversation.
- **Live** means that agent has connected to Codex app-server.
- An error means the app could not complete the connection or action; read the agent's conversation log for details.

Select **Demo activity** or **Codex agents** in the project controls. In Codex mode, configured thread IDs resume; agents without an ID get a new conversation. A failure for one agent should not make other agents appear disconnected or simulated.

The app launches `codex app-server` locally by default. For a different local command, set `app_server_command` in the `config.json` beside the app's `main.py` and restart. This is an advanced transport override. Read the official [Codex app-server documentation](https://learn.chatgpt.com/docs/app-server) for protocol details. Do not expose an unauthenticated app-server listener to the network.

Interactive approval and user-input requests from app-server are not approved by Mission Control. The desktop currently has no approval UI; it reports the request and leaves the action unapproved. Continue such work in a workflow that can present the approval.

## Where configuration lives

The folder containing `main.py`, `run.command`, and `run.bat` is the app folder. `workspace.json` stores the project list and source choices. The app's `data/projects/<project-id>/` directories store each managed roster and instruction files; reusable team presets are stored with the app state. Back up `workspace.json` and `data/` together.

The top-level `agents.json`, `config.json`, and `.codex/agents/*.toml` beside `main.py` are import defaults on first startup. After migration, use **Manage team...** or **Open team JSON** for the active project's current roster and instructions. The `config.json` beside `main.py` can configure an alternate app-server command; source selection is managed per project in the app.

For example, a managed agent entry uses stable IDs to describe its links and model settings:

```json
{
  "id": "orchestrator",
  "model": "gpt-6-astra",
  "reasoning_effort": "medium",
  "linked_agent_ids": ["frontend", "backend"]
}
```

Edit the active project's actual file with **Open team JSON**, preserve `id`, instruction paths, and internal fingerprint/generation fields, then choose **Reload team JSON**. Prefer **Attach conversation...** to change a thread ID safely. Keep a backup before editing JSON by hand.

## Troubleshooting

- **The launcher exits during setup:** Check that Python 3.11+ is installed and the first-run internet connection is available. Run the launcher from Terminal or Command Prompt to read the error.
- **macOS blocks `run.command`:** Control-click it and choose **Open**. If needed, run `chmod +x run.command` from Terminal in the app folder.
- **You expected the app in Chrome:** Mission Control is a desktop application, not a web server. Check the Terminal or command window for launch errors.
- **Codex agents stay Connecting or show an error:** Confirm the Codex CLI is installed, run `codex` to complete sign-in if requested, verify the selected project folder exists, and check the agent's log. Check account access for the selected model. For a different local executable, configure `app_server_command` beside `main.py`.
- **Handoff is unavailable or fails:** Confirm the caller has the target listed in **Linked teammates**, the target is not already busy, and Codex app-server supports the experimental dynamic-tool API.
- **A JSON reload fails:** Restore a valid backup or fix the reported field, then reload again. Do not delete managed instruction files or change their paths in JSON.
- **You want to try the app safely:** Select **Demo activity**; it makes no model calls.

## Screenshots and tests

With the app dependencies installed, run:

```sh
python -m pytest
```

Capture the overview, agent conversations, team settings, and Setup Guide without opening a normal desktop window:

```sh
QT_QPA_PLATFORM=offscreen python main.py --screenshot /tmp/mission-control.png
```

See `CONTRACT.md` for the app-server protocol, workspace persistence rules, and visual requirements.
