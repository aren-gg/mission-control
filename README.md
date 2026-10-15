# Underwater Agent Office

Underwater Agent Office is a small desktop dashboard for checking the current status, tool activity, and messages for your configured agents. It supports a simulated **Mock** source and a **Codex app-server** source.

## Start the app

### macOS

1. Open this project folder in Finder.
2. Double-click `run.command`.
3. The first launch creates a Python environment and installs the app's dependencies. This can take a few minutes and requires an internet connection.
4. The desktop office opens when setup finishes. Keep the Terminal window open while using the app; closing it stops the app.

If macOS says the launcher cannot be opened, control-click `run.command`, choose **Open**, and confirm. If needed, open Terminal in this folder and run `chmod +x run.command` once, then double-click it again.

### Windows

1. Open this project folder in File Explorer.
2. Double-click `run.bat`.
3. The first launch creates a Python environment and installs the app's dependencies. This can take a few minutes and requires an internet connection.
4. Keep the command window open while using the app; closing it stops the app.

### Start it from Terminal

If Python is already installed, open a terminal in the project folder and run:

```sh
python main.py
```

On macOS, you may need to use `python3 main.py` instead.

## Choose the activity source

Edit `config.json` in a text editor. Set `source` to `mock` for sample activity, or `codex` to connect to the local Codex app-server. Save the file and restart the app after changing it. The app starts in mock mode when the setting is missing or invalid.

In Codex mode, the app resumes an agent's configured `app_server_thread_id`. If that field is blank or `null`, it starts a Codex thread using that agent's model and role, then saves the new ID to `agents.json` for next time. If one agent cannot connect, that agent alone falls back to mock activity and is clearly marked `DEMO`; the other connected agents continue normally.

Codex app-server integration uses a local process/connection and is experimental. The configured app-server command in `config.json` is optional; by default the app launches `codex app-server`. Use the official [Codex app-server documentation](https://learn.chatgpt.com/docs/app-server) for setup and protocol details. Do not expose the app-server on an unauthenticated network listener.

## Edit the roster

Edit `agents.json` with a text editor. It must be a JSON array with 1 to 8 agents. Each entry needs:

- A unique lowercase `id`, such as `backend`.
- A display `name`, `role`, and `model`.
- A `species` from `blue_whale`, `beluga`, `orca`, `sperm_whale`, `humpback`, or `narwhal`.
- An `accent_color` from the 16-color palette in `CONTRACT.md`.
- Optional `app_server_thread_id` (use `null` for mock activity).

Keep the same ID when you edit an agent; it identifies that agent's history and Codex thread mapping. Restart the app after changing the roster. If the JSON is invalid, check commas, quotation marks, and brackets, then try again.

## Tests and screenshots

With the project dependencies installed, run:

```sh
python -m pytest
```

To save screenshots of the Office and agent tabs without opening a window:

```sh
QT_QPA_PLATFORM=offscreen python main.py --screenshot screenshots/office.png
```

The app saves one PNG for the office plus one deterministic PNG for each agent tab beside the requested output. See `CONTRACT.md` for the visual and event details.
# mission-control
