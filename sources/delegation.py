"""Bounded cross-thread delegation. JSON-RPC reading never waits for a task."""
from concurrent.futures import Future, TimeoutError
import json
import threading
import time
from uuid import uuid4
from .base import make_event


class DelegationMixin:
    def _init_delegation(self, timeout=600):
        self.delegation_timeout = max(.05, float(timeout))
        self._active_tasks = {}
        self._busy_agents = set()
        self._waiting_on = {}
        self._tool_workers = set()
        self._tool_request_ids = set()

    def automatic_delegation_available(self, agent_id):
        agent = next(a for a in self.agents if a['id'] == agent_id)
        return agent.get('delegation_tool_version') == 1 and not self.is_demo(agent_id)

    def _delegation_tool(self):
        return {'type': 'function', 'name': 'delegate_to_agent',
            'description': 'Delegate a concrete task to an explicitly linked teammate and wait for its completed public result. Uses that teammate\'s independent conversation. Do not delegate to busy teammates or create dependency cycles.',
            'inputSchema': {'type': 'object', 'properties': {'agent_id': {'type': 'string'}, 'content': {'type': 'string'}},
                            'required': ['agent_id', 'content'], 'additionalProperties': False}}

    def _delegation_instructions(self, agent):
        if agent.get('app_server_thread_id') and agent.get('delegation_tool_version') != 1:
            return '\nAutomatic team delegation is unavailable in this older conversation. Do not invoke delegate_to_agent. The user can use explicit manual handoffs or start a new conversation.'
        ids = agent.get('linked_agent_ids', [])
        if not ids:
            return '\nNo teammates are currently linked. Do not invoke delegation.'
        return '\nYou may use delegate_to_agent only for these linked agent IDs: ' + ', '.join(ids) + '. Delegate concrete tasks; read and integrate the returned completion. Their models, instructions and conversations remain independent. Ordinary user replies go only to this conversation.'

    def _cycle(self, sender, target):
        pending = [target]
        seen = set()
        while pending:
            node = pending.pop()
            if node == sender:
                return True
            if node not in seen:
                seen.add(node)
                pending.extend(self._waiting_on.get(node, set()))
        return False

    def _reserve_task(self, target, content, sender=None):
        with self._lock:
            if self._stop.is_set():
                raise RuntimeError('Event source is closed')
            if target not in self._ready or target in self._demo_agents:
                raise RuntimeError('Target Codex agent is not connected; live work cannot be delegated to demo activity')
            if sender and self._cycle(sender, target):
                raise RuntimeError('Delegation cycle rejected')
            if target in self._busy_agents:
                raise RuntimeError('Target agent is busy; wait for its current turn to complete')
            future = Future()
            context = {'id': str(uuid4()), 'target': target, 'sender': sender, 'content': content,
                       'future': future, 'messages': {}, 'turn_id': None, 'deadline': time.monotonic() + self.delegation_timeout,
                       'expired': False}
            self._active_tasks[target] = context
            self._busy_agents.add(target)
            if sender:
                self._waiting_on.setdefault(sender, set()).add(target)
            return context

    def delegate_message(self, from_agent_id, to_agent_id, content, *, _automatic=False):
        content = self._check_delegation(from_agent_id, to_agent_id, content)
        if from_agent_id in self._demo_agents or from_agent_id not in self._ready:
            raise RuntimeError('Sending agent must be connected to Codex for live delegation')
        context = self._reserve_task(to_agent_id, content, from_agent_id)
        routed = self._delegation_started(from_agent_id, to_agent_id, content, context['id'], automatic=_automatic)
        context['content'] = routed
        self._user_echoes.setdefault(to_agent_id, []).append(routed)
        self._outbox.put(context)
        return context['future']

    def _submit_user(self, agent_id, content):
        context = self._reserve_task(agent_id, content)
        message_id = self._user_message(agent_id, content)
        self._user_echoes.setdefault(agent_id, []).append(content)
        self._outbox.put(context)
        return message_id

    def _finish_task(self, agent_id, error=None, release=True):
        with self._lock:
            context = self._active_tasks.get(agent_id)
            if release:
                self._active_tasks.pop(agent_id, None)
                self._busy_agents.discard(agent_id)
            if context is None:
                return
            sender = context['sender']
            if sender:
                self._waiting_on.get(sender, set()).discard(agent_id)
            future = context['future']
            if future.done():
                return
            text = '\n\n'.join(context['messages'].values()).strip()
            if not error and sender and not text:
                error = 'Target completed without an assistant response'
            if sender:
                self._delegation_result(sender, agent_id, str(error) if error else text, context['id'], failed=bool(error))
            if error:
                future.set_exception(RuntimeError(str(error)))
            else:
                future.set_result(text)

    def _track_notification(self, method, params):
        if not isinstance(params, dict):
            return
        thread = params.get('threadId')
        agent = self._thread_agents.get(thread)
        if not agent:
            return
        with self._lock:
            context = self._active_tasks.get(agent)
            supplied_turn = params.get('turnId')
            if context and context['turn_id'] and supplied_turn and context['turn_id'] != supplied_turn:
                return
            if method == 'turn/started':
                self._busy_agents.add(agent)
                if context:
                    context['turn_id'] = params.get('turn', {}).get('id') or params.get('turnId')
            elif method == 'item/agentMessage/delta' and context:
                item_id = params.get('itemId', 'stream')
                context['messages'][item_id] = context['messages'].get(item_id, '') + str(params.get('delta', ''))
            elif method == 'item/completed' and context:
                item = params.get('item', {})
                if item.get('type') == 'agentMessage':
                    context['messages'][item.get('id', 'stream')] = item.get('text', '')
            elif method == 'turn/completed':
                turn = params.get('turn', {})
                if context and context['turn_id'] and turn.get('id') and context['turn_id'] != turn['id']:
                    return
                status = turn.get('status', 'completed')
                error = turn.get('error') or (f'Target turn {status}' if status in ('failed', 'interrupted', 'cancelled') else None)
                self._finish_task(agent, error)
            elif method == 'error' and not params.get('willRetry', False):
                detail = params.get('error', {})
                self._finish_task(agent, detail.get('message', 'Codex reported a terminal error') if isinstance(detail, dict) else str(detail))
            elif method in ('thread/closed', 'thread/archived'):
                self._finish_task(agent, 'Target conversation closed before work completed')
            elif method == 'thread/status/changed':
                status = params.get('status', {}).get('type')
                if status == 'active':
                    self._busy_agents.add(agent)
                elif status == 'systemError':
                    self._finish_task(agent, 'Target conversation entered an error state')
                elif status == 'idle' and context is None:
                    self._busy_agents.discard(agent)

    def _start_queued_task(self, context):
        target = context['target']
        if context['future'].done() or self._stop.is_set():
            self._finish_task(target, 'Task cancelled before starting')
            return
        if target not in self._ready:
            self._finish_task(target, 'Agent disconnected before message was sent')
            return
        thread = next(a['app_server_thread_id'] for a in self.agents if a['id'] == target)
        try:
            result = self._rpc('turn/start', {'threadId': thread, 'input': [{'type': 'text', 'text': context['content']}]})
            if not context['turn_id']:
                context['turn_id'] = result.get('turn', {}).get('id')
        except Exception as exc:
            from .codex import RpcError
            definite_rejection = isinstance(exc, RpcError)
            self._finish_task(target, str(exc), release=definite_rejection)
            self._publish(make_event(target, 'error', message='Codex rejected the message', detail=str(exc)))

    def _expire_tasks(self):
        with self._lock:
            expired = [c for c in self._active_tasks.values() if c['sender'] and not c['expired'] and time.monotonic() >= c['deadline']]
        for context in expired:
            context['expired'] = True
            self._finish_task(context['target'], 'Delegation timed out; target remains busy until its turn ends', release=False)

    def _fail_tasks(self, reason):
        with self._lock:
            ids = list(self._active_tasks)
        for target in ids:
            self._finish_task(target, reason)
        with self._lock:
            self._waiting_on.clear()
            self._busy_agents.clear()

    def _handle_tool_request(self, message, process):
        key = (id(process), message['id'])
        with self._lock:
            if key in self._tool_request_ids:
                return
            if len(self._tool_workers) >= 16:
                self._write_tool_result(message['id'], False, 'Too many concurrent delegation requests', process)
                return
            self._tool_request_ids.add(key)
            worker = threading.Thread(target=self._tool_worker, args=(message, process), name='delegate-to-agent', daemon=True)
            self._tool_workers.add(worker)
        worker.start()

    def _write_tool_result(self, request_id, success, text, process):
        # Request IDs are scoped to their connection. Never send an old tool
        # result to a replacement process after reconnecting.
        with self._write_lock:
            if self._stop.is_set() or process is not self._process or process.poll() is not None:
                raise ConnectionError('Tool request belongs to a closed connection')
            response = {'id': request_id, 'result': {'success': success,
                'contentItems': [{'type': 'inputText', 'text': text[:100000]}]}}
            process.stdin.write(json.dumps(response, ensure_ascii=False) + '\n')
            process.stdin.flush()

    def _tool_worker(self, message, process):
        try:
            if self._stop.is_set() or process is not self._process:
                raise RuntimeError('Tool request belongs to a closed connection')
            params = message.get('params', {})
            if params.get('tool') != 'delegate_to_agent':
                raise ValueError('Unknown dashboard tool')
            sender = self._thread_agents.get(params.get('threadId'))
            if not sender:
                raise ValueError('Unknown calling conversation')
            with self._lock:
                active = self._active_tasks.get(sender)
                if active and active.get('turn_id') and params.get('turnId') and params['turnId'] != active['turn_id']:
                    raise ValueError('Tool request does not belong to the current turn')
            arguments = params.get('arguments', {})
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            if not isinstance(arguments, dict):
                raise ValueError('Tool arguments must be an object')
            future = self.delegate_message(sender, arguments.get('agent_id'), arguments.get('content'), _automatic=True)
            text = future.result(timeout=self.delegation_timeout + 2)
            self._write_tool_result(message['id'], True, text, process)
        except Exception as exc:
            try:
                self._write_tool_result(message['id'], False, str(exc) or 'Delegation failed', process)
            except (OSError, RuntimeError, ValueError):
                pass
        finally:
            with self._lock:
                self._tool_request_ids.discard((id(process), message['id']))
                self._tool_workers.discard(threading.current_thread())
