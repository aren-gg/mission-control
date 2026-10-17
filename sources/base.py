"""Thread-safe event source interface consumed directly by the Qt signal bridge."""
from __future__ import annotations
import copy
import logging
import threading
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from concurrent.futures import Future
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

Event = dict
HISTORY_LIMIT = 1000


def utc_timestamp(value=None):
    if isinstance(value, str) and value:
        return value
    if isinstance(value, (float, int)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def make_event(agent_id, event_type, timestamp=None, **data):
    return {'type': event_type, 'agent_id': agent_id, 'timestamp': utc_timestamp(timestamp), 'data': data}


class AgentEventSource(ABC):
    mode = 'mock'

    def __init__(self, agents):
        self.agents = copy.deepcopy(agents)
        self._ids = {a['id'] for a in self.agents}
        self._history = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))
        self._callbacks: list[Callable] = []
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._started = False

    @property
    def roster(self):
        return self.agents

    def get_history(self, agent_id):
        if agent_id not in self._ids:
            raise ValueError('Unknown agent: ' + str(agent_id))
        with self._lock:
            return copy.deepcopy(sorted(self._history[agent_id], key=lambda event: event['timestamp']))

    history = get_history

    def subscribe(self, callback):
        with self._lock:
            self._callbacks.append(callback)
        def unsubscribe():
            with self._lock:
                if callback in self._callbacks:
                    self._callbacks.remove(callback)
        return unsubscribe

    def _publish(self, event):
        if event.get('agent_id') not in self._ids or self._stop.is_set():
            return
        with self._lock:
            events = self._history[event['agent_id']]
            message_id = event.get('data', {}).get('message_id') if event['type'] == 'message' else None
            existing = next((i for i, e in enumerate(events) if message_id and e['type'] == 'message' and e['data'].get('message_id') == message_id), None)
            if existing is None:
                events.append(copy.deepcopy(event))
            else:
                events[existing] = copy.deepcopy(event)
            callbacks = list(self._callbacks)
        for callback in callbacks:
            try:
                callback(copy.deepcopy(event))
            except Exception:
                logging.exception('Event subscriber failed')

    def _status(self, agent_id, status, summary, timestamp=None):
        self._publish(make_event(agent_id, 'status_change', timestamp, status=status, summary=summary[:40]))

    def _validate_message(self, agent_id, content):
        if agent_id not in self._ids:
            raise ValueError('Unknown agent: ' + str(agent_id))
        if not isinstance(content, str) or not content.strip():
            raise ValueError('Message cannot be blank')
        if self._stop.is_set():
            raise RuntimeError('Event source is closed')
        return content.strip()

    def _user_message(self, agent_id, content):
        event = make_event(agent_id, 'message', message_id=str(uuid4()), role='user', content=content)
        self._publish(event)
        return event['data']['message_id']

    def _check_delegation(self, from_agent_id, to_agent_id, content):
        content = self._validate_message(to_agent_id, content)
        if from_agent_id not in self._ids:
            raise ValueError('Unknown sending agent')
        if from_agent_id == to_agent_id:
            raise ValueError('An agent cannot delegate to itself')
        sender = next(a for a in self.agents if a['id'] == from_agent_id)
        if to_agent_id not in sender.get('linked_agent_ids', []):
            raise ValueError('This teammate is not linked; enable the directed link in Team settings')
        return content

    def _delegation_started(self, from_agent_id, to_agent_id, content, delegation_id, automatic=False):
        for agent_id, name in ((from_agent_id, 'Delegation sent'), (to_agent_id, 'Delegation received')):
            self._publish(make_event(agent_id, 'tool_call', tool='other', name=name,
                summary=f'{from_agent_id} -> {to_agent_id}', from_agent_id=from_agent_id,
                to_agent_id=to_agent_id, delegation_id=delegation_id))
        self._publish(make_event(from_agent_id, 'message', message_id='sent-' + delegation_id,
            role='assistant' if automatic else 'user', content=f'[Handoff to {to_agent_id}]\n{content}', delegation_to=to_agent_id))
        event = make_event(to_agent_id, 'message', message_id=delegation_id, role='user',
                           content=f'[Delegated from {from_agent_id}]\n{content}', delegation_from=from_agent_id)
        self._publish(event)
        return event['data']['content']

    def _delegation_result(self, from_agent_id, to_agent_id, text, delegation_id, failed=False):
        if failed:
            for agent_id in (from_agent_id, to_agent_id):
                self._publish(make_event(agent_id, 'error', message='Delegation failed', detail=text,
                                         delegation_id=delegation_id))
        else:
            self._publish(make_event(from_agent_id, 'message', message_id='result-' + delegation_id,
                role='assistant', content=f'[Result from {to_agent_id}]\n{text}', delegation_from=to_agent_id))
        waiting = bool(getattr(self, '_waiting_on', {}).get(from_agent_id))
        busy = from_agent_id in getattr(self, '_busy_agents', set())
        self._status(from_agent_id, 'waiting' if waiting else ('working' if busy else 'idle'),
                     'Waiting on teammates' if waiting else ('Continuing current task' if busy else ('Handoff failed' if failed else 'Handoff complete')))

    def delegate_message(self, from_agent_id, to_agent_id, content):
        raise NotImplementedError('This source does not support delegation')

    def is_demo(self, agent_id):
        return True

    @abstractmethod
    def start(self): ...

    @abstractmethod
    def send_message(self, agent_id, content): ...

    def close(self):
        self._stop.set()
