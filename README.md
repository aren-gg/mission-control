# Underwater Agent Office

Underwater Agent Office is a local desktop dashboard for keeping separate Codex conversations organized by project and role. It is a PySide6 desktop app, **not a website**: it does not run a localhost server or open Chrome. You can have Chrome open normally, but use the desktop window to view and control this app.

The app starts in **Demo activity** mode. Demo activity is simulated and makes no model calls. Switching to **Codex agents** connects or creates Codex conversations for the selected project's agents. Startup by itself does not start implementation work: after the agents connect, open the Orchestrator or a specialist tab and send it a concrete task.

## Start the desktop app

Install Python 3.11 or newer first. The first launch needs an internet connection to install the Python packages.

### macOS

1. In Finder, open the project folder.
2. Double-click `run.command`.
3. If macOS blocks it, control-click `run.command`, choose **Open**, and confirm. If Finder says the file is not executable, open Terminal in the folder and run `chmod +x run.command` once.
4. Wait for setup to finish and the desktop window to open. Keep the Terminal window open while using the app; closing it stops the app.

### Windows

1. In File Explorer, open the project folder.
2. Double-click `run.bat`.
3. Wait for setup to finish and the desktop window to open. Keep the command window open while using the app; closing it stops the app.

For a manual start, open a terminal in the project folder, install `requirements.txt` into a Python 3.11+ environment, then run `python main.py` (on macOS, `python3 main.py`).

## Create your first project

1. Start the app. The **Office** tab shows the roster and simulated activity.
2. Use **Add project...** to choose your existing code folder. Give the project a short display name and, if offered, choose a team preset. The project path is the working directory Codex will use.
3. Select the new project from the project selector. Project rosters, instructions, source settings, and thread IDs are isolated from your other projects.
4. Open **Manage team...** to add, edit, or remove team members. Start with the included Orchestrator, Front End, Back End, and Mission Control team, or create a smaller team. Save changes in the editor.
5. Select **Demo activity** to explore the UI without model calls. Click an agent tab, enter a test request, and press **Enter** (use **Shift+Enter** to add a line). The message goes only to the selected agent.
6. When you are ready to use Codex, select **Codex agents**. Watch the top-right connection badge for **LIVE**, **CONNECTING**, or **DEMO** counts. A configured thread may briefly show **Connecting** in its tab. If Codex cannot connect for one agent, its tab shows a visible error and **DEMO** status.
7. Open the **Orchestrator** tab and send a concrete task, for example: “Inspect this project and propose the first three implementation tasks. Do not edit files yet.” To delegate a focused task, open **Back End** or **Front End** and message that specialist directly. To reference files, choose **Reference files...** beside the message title; it adds selected project-relative paths to the unsent draft. Review the draft and send it when ready. The picker references files in the selected project; it does not upload or read their contents.

Each visible agent tab represents its own thread and conversation. The Orchestrator may start native Codex subagents inside its own conversation, but those subagents are not automatically separate dashboard tabs or automatically mapped to the other visible agents. Message a specialist tab directly when you want that configured agent's separate conversation to act on a task.

## Before using Codex agents

Install the [Codex CLI](https://learn.chatgpt.com/docs/codex/cli), open Terminal or Command Prompt, run `codex` once, and complete sign-in if prompted. Then open or restart Underwater Agent Office and select **Codex agents**. You need account access to each model selected for your team; access can vary by account.

The app runs one active project team at a time. Switching projects while agents are working asks you to confirm because reconnecting can interrupt their current work.

## Projects and working folders

Use the **Project** selector to switch between projects. **Add project...** opens a folder picker; select an existing repository or another folder you want Codex to work in. **Open folder** opens the selected path in Finder or File Explorer. Confirm the displayed absolute path before switching to Codex mode, because that selected folder becomes the Codex working directory.

Each project's team and source mode are independent. Switching projects closes the previous project's event source and starts the selected project's source. Project configuration and instruction text are stored in the app's managed data folder, not written into the selected code folder. The app does not modify another project's files when you edit configuration.

## Manage agents and instructions

Open **Manage team...** for the selected project.

- **Add agent** creates a team member. Select an existing agent in the list to edit its fields; **Remove** deletes that agent from this project's roster. Between 1 and 8 agents must remain.
- Set the display name, role, model, reasoning effort, whale species, and accent color. Agent IDs remain stable when you rename an agent.
- Edit the agent's multiline instructions in the instruction editor. The editor shows the managed instruction file path. Use **Open instruction file** to open that file in your text editor; after editing it externally, use **Reload external edits** to read those changes back before saving.
- Save validates the roster and instructions. If the editor shows an error, correct the named field and save again.
- Model, reasoning effort, role, or instruction changes start a fresh Codex conversation the next time this agent connects. The previous Codex conversation is retained by Codex. Cosmetic changes such as the display name, whale species, or accent color preserve the current thread.

Existing `agents.json`, `config.json`, and `.codex/agents/*.toml` beside the app's `main.py` are imported as defaults on first startup. After migration, use the in-app editor as the current source of truth for managed instructions. The selected project's roster and thread IDs are saved with app-managed project state. The app folder's `config.json` is a legacy import default for the source choice; changing it after migration does not replace the in-app source selection. Codex file references always resolve within the selected code project.

## Reuse a team with presets

In **Manage team...**, choose **Save team as preset...**, enter a name, and optionally make it the default team for new projects. A preset stores agent settings and instructions, but never Codex thread IDs or project paths.

Choose a preset when adding a project, or select **Apply preset...** to replace the current project's team. Applying a preset replaces that project's roster and instructions, so confirm the replacement in the app when prompted. Editing a project copied from a preset does not alter the saved preset or any other project's team.

## Demo and Codex connection states

- **DEMO** means the activity is simulated. It is safe to use for exploring, and it never represents a live Codex thread.
- **Connecting** means the app is starting or resuming that agent's Codex thread.
- **Live** means that agent is connected to Codex app-server.

Select **Demo activity** or **Codex agents** in the app. The default is Demo. In Codex mode, an agent with a saved thread ID resumes it. If its ID is empty, the app starts a thread with its selected model, reasoning effort, and role instructions, then saves the new ID for the next launch. If one thread cannot connect, only that agent falls back to Demo and is marked **DEMO** with an error.

The app launches `codex app-server` locally by default. For an alternate local executable, set `app_server_command` in the `config.json` beside `main.py` (for example, `["/path/to/codex", "app-server"]`) and restart the app. This is an advanced transport override; source selection still happens in the app. Codex app-server is experimental; use the official [Codex app-server documentation](https://learn.chatgpt.com/docs/app-server) for setup and protocol details. Do not expose an unauthenticated app-server listener to the network.

### Where project and agent settings are stored

The folder containing `main.py` and the launchers is the app folder. Its `workspace.json` stores the project list, source choices, and team presets. Project-specific rosters and managed instruction files are under `data/projects/<project-id>/` in that app folder; the selected code folder remains the Codex working directory and is not used to store these settings. Back up `workspace.json` and `data/` together to preserve your projects and teams. The top-level `agents.json`, `config.json`, and `.codex/agents/*.toml` are first-start import defaults; after migration, use **Manage team...** for current agent settings and instructions.

## Troubleshooting

- **The launcher window closes or says setup failed:** Make sure Python 3.11+ is installed and your internet connection works. Re-run the launcher from Terminal/Command Prompt so you can read the full error.
- **macOS will not open `run.command`:** Control-click it and choose **Open**. If it is not executable, run `chmod +x run.command` from Terminal in the project folder.
- **The desktop app does not appear in Chrome:** That is expected. This is a desktop app, not a browser site. Check whether the Terminal or command window reports an error.
- **Codex agents stay Connecting or switch to DEMO:** Check that the Codex CLI is installed and available as `codex` in the launch environment, that app-server can start, and that the selected project path exists and is accessible. The agent's activity log includes its connection error. To use another local executable, set `app_server_command` in the `config.json` beside `main.py` and restart the app.
- **A thread is using old behavior:** Change the agent's model, reasoning effort, role, or instructions and save; the app starts a fresh thread on the next Codex connection. Use **New conversation...** to start fresh without changing the agent settings.
- **You cannot save an agent:** Check that the name and role are filled in, the model and effort are supported, IDs are unique, and the roster contains 1 to 8 agents.
- **External instruction edits do not appear:** Use **Reload external edits** in the instruction editor, then save the agent.
- **You want to try the app safely:** Select **Demo activity**. It does not call a model or change project source files.

## Capture screenshots and run tests

With the app dependencies installed, run the tests:

```sh
python -m pytest
```

Save an Office screenshot and one screenshot per agent without opening a normal desktop window:

```sh
QT_QPA_PLATFORM=offscreen python main.py --screenshot screenshots/office.png
```

See `CONTRACT.md` for the event protocol, workspace persistence rules, and visual requirements.
