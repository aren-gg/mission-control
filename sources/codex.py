"""Local Codex app-server JSONL adapter.

Protocol: https://learn.chatgpt.com/docs/app-server
No network listener is opened. Each role maps to a configured or newly created
thread. Mock fallbacks are explicit, per agent, and never masquerade as live.
"""
from __future__ import annotations
import json
import logging
import os
import queue
import shutil
import subprocess
import threading
import tomllib
from collections import deque
from pathlib import Path
from .base import AgentEventSource, make_event
from .mock import MockEventSource


class RpcError(RuntimeError):
    pass


def default_command():
    executable = shutil.which('codex')
    bundled = Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
    if not executable and bundled.is_file():
        executable = str(bundled)
    return [executable or 'codex', 'app-server', '--listen', 'stdio://']


class CodexAppServerSource(AgentEventSource):
    mode = 'codex'

    def __init__(self, agents, command=None, reconnect_delay=1.0, project_root=None, roster_path=None, request_timeout=20):
        super().__init__(agents)
        self.command = command or default_command()
        self.project_root = Path(project_root or Path.cwd()).resolve()
        self.roster_path = Path(roster_path) if roster_path else None
        self.reconnect_delay = max(.05, float(reconnect_delay))
        self.request_timeout = max(.1, float(request_timeout))
        self._process = None
        self._worker = None
        self._reader = None
        self._write_lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._request_id = 0
        self._pending = {}
        self._outbox = queue.Queue()
        self._ready = set()
        self._ever_connected = set()
        self._thread_agents = {}
        self._demo_agents = set()
        self._mock = None
        self._texts = {}
        self._message_timestamps = {}
        self._seen_items = set()
        self._user_echoes = {}
        self._stderr = deque(maxlen=12)

    def is_demo(self, agent_id):
        return agent_id in self._demo_agents

    def start(self):
        if self._started or self._stop.is_set():
            return
        self._started = True
        for agent in self.agents:
            self._status(agent['id'], 'waiting', 'Connecting to Codex app-server')
        self._worker = threading.Thread(target=self._run, name='codex-app-server', daemon=True)
        self._worker.start()

    def _write(self, message):
        with self._write_lock:
            process = self._process
            if not process or process.poll() is not None:
                raise ConnectionError('App-server is not connected')
            process.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
            process.stdin.flush()

    def _rpc(self, method, params):
        with self._request_lock:
            self._request_id += 1
            request_id = self._request_id
            ready = threading.Event()
            holder = {}
            self._pending[request_id] = (ready, holder)
        try:
            self._write({'id': request_id, 'method': method, 'params': params})
            if not ready.wait(self.request_timeout):
                raise ConnectionError('Timed out waiting for ' + method)
            if 'error' in holder:
                raise RpcError(str(holder['error']))
            return holder.get('result', {})
        finally:
            with self._request_lock:
                self._pending.pop(request_id, None)

    def _read_stdout(self, process):
        try:
            for line in process.stdout:
                if self._stop.is_set():
                    break
                try:
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        continue
                    if 'id' in message and 'method' not in message:
                        with self._request_lock:
                            pending = self._pending.get(message['id'])
                        if pending:
                            pending[1].update(message)
                            pending[0].set()
                    elif 'id' in message:
                        # Approval and interactive questions require a human UI.
                        # Never silently approve a server-initiated action.
                        self._write({'id': message['id'], 'error': {'code': -32601,
                                     'message': 'Handle approvals and interactive input in Codex; this dashboard has no approval dialog.'}})
                        agent_id = self._thread_agents.get(message.get('params', {}).get('threadId'))
                        if agent_id:
                            self._status(agent_id, 'waiting', 'Action needs attention in Codex')
                            self._publish(make_event(agent_id, 'error', message='Interactive request needs Codex',
                                                     detail=message.get('method', 'Unknown request')))
                    elif 'method' in message:
                        self._notification(message['method'], message.get('params', {}))
                except (json.JSONDecodeError, TypeError, KeyError, ValueError):
                    logging.warning('Ignored malformed app-server notification', exc_info=True)
        except (OSError, ValueError):
            pass
        finally:
            with self._request_lock:
                pending = list(self._pending.values())
            for ready, holder in pending:
                holder['error'] = 'App-server disconnected'
                ready.set()

    def _read_stderr(self, process):
        try:
            for line in process.stderr:
                self._stderr.append(line.strip()[:500])
        except (OSError, ValueError):
            pass

    def _start_params(self, agent):
        instructions = f"You are {agent['name']}. Your role: {agent['role']}. Work within the current project and report public progress clearly."
        params = {'model': agent['model'], 'cwd': str(self.project_root)}
        filenames = {'orchestrator': 'orchestrator.toml', 'frontend': 'frontend-implementor.toml',
                     'backend': 'backend-implementor.toml', 'mission_control': 'mission-control.toml'}
        filename = filenames.get(agent['id'])
        if filename:
            path = self.project_root / '.codex' / 'agents' / filename
            try:
                role = tomllib.loads(path.read_text(encoding='utf-8'))
                if isinstance(role.get('developer_instructions'), str):
                    instructions += '\n\n' + role['developer_instructions']
                effort = role.get('model_reasoning_effort')
                if effort in ('low', 'medium', 'high', 'xhigh', 'max', 'ultra', 'minimal', 'none'):
                    params['config'] = {'model_reasoning_effort': effort}
            except (OSError, ValueError):
                pass
        params['developerInstructions'] = instructions
        return params

    def _persist_ids(self):
        if not self.roster_path:
            return
        # Read again so unrelated roster edits are not overwritten.
        roster = json.loads(self.roster_path.read_text(encoding='utf-8'))
        mapping = {a['id']: a.get('app_server_thread_id') for a in self.agents}
        for agent in roster:
            if agent['id'] in mapping and mapping[agent['id']]:
                agent['app_server_thread_id'] = mapping[agent['id']]
        self.roster_path.write_text(json.dumps(roster, indent=2) + '\n', encoding='utf-8')

    def _connect(self):
        self._process = subprocess.Popen(self.command, cwd=str(self.project_root), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self._reader = threading.Thread(target=self._read_stdout, args=(self._process,), daemon=True)
        self._reader.start()
        threading.Thread(target=self._read_stderr, args=(self._process,), daemon=True).start()
        self._rpc('initialize', {'clientInfo': {'name': 'underwater_agent_office', 'title': 'Underwater Agent Office', 'version': '1.0.0'}})
        self._write({'method': 'initialized', 'params': {}})
        for agent in self.agents:
            agent_id = agent['id']
            if agent_id in self._demo_agents:
                continue
            try:
                thread_id = agent.get('app_server_thread_id')
                if thread_id:
                    self._thread_agents[thread_id] = agent_id
                    result = self._rpc('thread/resume', {'threadId': thread_id, 'excludeTurns': True})
                else:
                    result = self._rpc('thread/start', self._start_params(agent))
                    thread_id = result.get('thread', {}).get('id')
                    if not isinstance(thread_id, str) or not thread_id:
                        raise RpcError('thread/start did not return a thread ID')
                    agent['app_server_thread_id'] = thread_id
                    self._thread_agents[thread_id] = agent_id
                    try:
                        self._persist_ids()
                    except (OSError, ValueError, TypeError) as exc:
                        self._publish(make_event(agent_id, 'error', message='Could not save new thread ID', detail=str(exc)))
                self._hydrate(agent_id, thread_id, result)
                self._ready.add(agent_id)
                self._ever_connected.add(agent_id)
                self._status(agent_id, 'idle', 'Live Codex thread connected')
            except RpcError as exc:
                self._fallback(agent_id, 'Could not connect this Codex thread', str(exc))

    def _hydrate(self, agent_id, thread_id, resumed):
        """Load oldest-first full turns via documented history pagination."""
        turns = resumed.get('thread', {}).get('turns', [])
        try:
            cursor = None
            seen_cursors = set()
            while True:
                params = {'threadId': thread_id, 'sortDirection': 'asc', 'itemsView': 'full', 'limit': 100}
                if cursor:
                    params['cursor'] = cursor
                result = self._rpc('thread/turns/list', params)
                for turn in result.get('data', []):
                    for item in turn.get('items', []):
                        self._map_item(agent_id, item, True, item.get('timestamp') or turn.get('createdAt'))
                cursor = result.get('nextCursor')
                if not cursor or cursor in seen_cursors or self._stop.is_set():
                    break
                seen_cursors.add(cursor)
        except RpcError as exc:
            # Older servers may return full turns in resume; use them only when
            # present, otherwise leave a visible diagnostic instead of fake history.
            for turn in turns:
                for item in turn.get('items', []):
                    self._map_item(agent_id, item, True, item.get('timestamp') or turn.get('createdAt'))
            if not turns:
                self._publish(make_event(agent_id, 'error', message='Stored history unavailable', detail=str(exc)))

    def _fallback(self, agent_id, message, detail):
        self._ready.discard(agent_id)
        self._demo_agents.add(agent_id)
        self._publish(make_event(agent_id, 'error', message=message + '; using DEMO', detail=detail))
        self._status(agent_id, 'error', 'DEMO fallback: Codex connection failed')
        if self._mock:
            self._mock.close()
        self._mock = MockEventSource([a for a in self.agents if a['id'] in self._demo_agents])
        self._mock.subscribe(self._publish)
        self._mock.start()

    def _run(self):
        attempt = 0
        while not self._stop.is_set():
            try:
                self._connect()
                attempt = 0
                while not self._stop.is_set():
                    if self._process.poll() is not None:
                        raise ConnectionError('App-server exited: ' + '\n'.join(self._stderr))
                    try:
                        agent_id, content = self._outbox.get(timeout=.2)
                    except queue.Empty:
                        continue
                    if agent_id not in self._ready:
                        self._publish(make_event(agent_id, 'error', message='Message was not sent; reconnect and try again'))
                        continue
                    thread_id = next(a['app_server_thread_id'] for a in self.agents if a['id'] == agent_id)
                    try:
                        self._rpc('turn/start', {'threadId': thread_id, 'input': [{'type': 'text', 'text': content}]})
                    except RpcError as exc:
                        self._publish(make_event(agent_id, 'error', message='Codex rejected the message', detail=str(exc)))
                        self._status(agent_id, 'error', 'Codex rejected the message')
            except (OSError, ConnectionError, RpcError, ValueError) as exc:
                self._ready.clear()
                attempt += 1
                delay = min(15, self.reconnect_delay * (2 ** min(attempt - 1, 4)))
                for agent in self.agents:
                    if agent['id'] not in self._demo_agents:
                        self._publish(make_event(agent['id'], 'error', message='Codex connection failed', detail=str(exc)))
                        self._status(agent['id'], 'error', f'Reconnecting in {delay:g}s')
                # Startup never worked: after bounded retries mark each fallback.
                if attempt >= 3:
                    for agent in self.agents:
                        if agent['id'] not in self._ever_connected and agent['id'] not in self._demo_agents:
                            self._fallback(agent['id'], 'Codex startup failed', str(exc))
                self._terminate()
                if len(self._demo_agents) == len(self.agents):
                    break
                if self._stop.wait(delay):
                    break
            finally:
                self._terminate()

    def _notification(self, method, params):
        if not isinstance(params, dict):
            return
        thread_id = params.get('threadId') or params.get('thread', {}).get('id')
        agent_id = self._thread_agents.get(thread_id)
        if not agent_id or agent_id in self._demo_agents:
            return
        stamp = params.get('timestamp') or params.get('createdAt')
        if method == 'turn/started':
            self._status(agent_id, 'working', 'Codex is working', stamp)
        elif method == 'turn/completed':
            turn = params.get('turn', {})
            failed = turn.get('status') == 'failed' or turn.get('error')
            self._status(agent_id, 'error' if failed else 'idle', 'Codex turn failed' if failed else 'Ready for your message', stamp)
            if failed:
                self._publish(make_event(agent_id, 'error', stamp, message='Codex turn failed', detail=str(turn.get('error', ''))))
        elif method in ('thread/status/changed', 'thread/started'):
            state = params.get('status') or params.get('thread', {}).get('status') or {'type': 'idle'}
            status = state.get('type', 'idle')
            flags = state.get('activeFlags', [])
            waiting = any(flag in ('waitingOnApproval', 'waitingOnUserInput') for flag in flags)
            mapped = 'waiting' if waiting else {'active': 'working', 'systemError': 'error', 'notLoaded': 'waiting'}.get(status, 'idle')
            self._status(agent_id, mapped, 'Codex needs your attention' if waiting else 'Codex thread: ' + status, stamp)
        elif method in ('thread/closed', 'thread/archived'):
            self._ready.discard(agent_id)
            self._status(agent_id, 'waiting', 'Codex thread is closed; restart app', stamp)
        elif method == 'item/agentMessage/delta':
            item_id = params.get('itemId', 'stream')
            key = (agent_id, item_id)
            self._texts[key] = self._texts.get(key, '') + str(params.get('delta', ''))
            timestamp = self._message_timestamps.setdefault(key, stamp or make_event(agent_id, 'message')['timestamp'])
            self._publish(make_event(agent_id, 'message', timestamp, message_id=item_id, role='assistant', content=self._texts[key]))
        elif method in ('item/started', 'item/completed'):
            self._map_item(agent_id, params.get('item', {}), method == 'item/completed', stamp)
        elif method == 'error':
            error = params.get('error', {})
            self._publish(make_event(agent_id, 'error', stamp, message=error.get('message', 'Codex error'), detail=str(error.get('additionalDetails', ''))))
            self._status(agent_id, 'error', 'Codex reported an error', stamp)
        elif method.startswith('item/') and ('outputDelta' in method or 'progress' in method.lower()):
            text = str(params.get('delta') or params.get('message') or 'Tool is running')
            self._status(agent_id, 'tool_call', text, stamp)

    def _map_item(self, agent_id, item, completed, timestamp=None):
        if not isinstance(item, dict):
            return
        kind = item.get('type', '')
        item_id = str(item.get('id', ''))
        key = (agent_id, item_id)
        if kind == 'agentMessage' and completed:
            text = item.get('text', '') or self._texts.get(key, '')
            previous = self._texts.get(key)
            if key not in self._seen_items and (text != previous or previous is None):
                self._publish(make_event(agent_id, 'message', self._message_timestamps.get(key, timestamp),
                                         message_id=item_id, role='assistant', content=text))
            self._texts[key] = text
            self._seen_items.add(key)
        elif kind == 'userMessage' and completed and key not in self._seen_items:
            content = '\n'.join(part.get('text', '') for part in item.get('content', []) if part.get('type') == 'text')
            # Accepted user input was already shown immediately; suppress its echo.
            echoes = self._user_echoes.get(agent_id, [])
            if content in echoes:
                echoes.remove(content)
            else:
                self._publish(make_event(agent_id, 'message', timestamp, message_id=item_id, role='user', content=content))
            self._seen_items.add(key)
        elif kind in ('commandExecution', 'fileChange', 'mcpToolCall', 'dynamicToolCall', 'webSearch', 'imageView', 'collabAgentToolCall', 'subAgentActivity'):
            if key in self._seen_items and completed:
                return
            tool = {'commandExecution': 'shell', 'fileChange': 'file', 'webSearch': 'browser'}.get(kind, 'other')
            name = item.get('command') or item.get('tool') or kind
            self._publish(make_event(agent_id, 'tool_call', timestamp, tool=tool, name=str(name),
                                     summary=(('Completed: ' if completed else 'Running: ') + str(name))[:40]))
            self._status(agent_id, 'working' if completed else 'tool_call', str(name), timestamp)
            if completed:
                self._seen_items.add(key)
                if item.get('status') in ('failed', 'declined') or item.get('exitCode', 0) not in (0, None):
                    self._publish(make_event(agent_id, 'error', timestamp, message='Tool action failed', detail=str(item.get('aggregatedOutput') or item.get('error') or name)))
                    self._status(agent_id, 'error', 'Tool action failed', timestamp)

    def send_message(self, agent_id, content):
        content = self._validate_message(agent_id, content)
        if agent_id in self._demo_agents:
            if not self._mock:
                raise RuntimeError('Demo fallback is starting; please try again.')
            return self._mock.send_message(agent_id, content)
        if agent_id not in self._ready:
            raise RuntimeError('Codex is not connected for this agent yet. Check its activity log.')
        message_id = self._user_message(agent_id, content)
        self._user_echoes.setdefault(agent_id, []).append(content)
        self._outbox.put((agent_id, content))
        return message_id

    def _terminate(self):
        process = self._process
        self._process = None
        if process:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream:
                    stream.close()

    def close(self):
        super().close()
        if self._mock:
            self._mock.close()
        self._terminate()
        if self._worker and self._worker is not threading.current_thread():
            self._worker.join(timeout=2)
