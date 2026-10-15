"""Explicitly simulated activity; never labeled as a live Codex session."""
import queue
import threading
from uuid import uuid4
from .base import AgentEventSource, make_event


class MockEventSource(AgentEventSource):
    def __init__(self, agents, interval=3.5):
        super().__init__(agents)
        self.interval = max(0.01, float(interval))
        self._messages = queue.Queue()
        self._thread = None
        self._step = 0

    def start(self):
        if self._started or self._stop.is_set():
            return
        self._started = True
        for agent in self.agents:
            if getattr(self, 'config_warning', None):
                self._publish(make_event(agent['id'], 'error', message='Invalid config; using DEMO', detail=self.config_warning))
            self._status(agent['id'], 'idle', 'Demo: ready at the desk')
        self._thread = threading.Thread(target=self._run, name='mock-agent-source', daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                message = self._messages.get(timeout=self.interval)
                if message is None:
                    break
                agent_id, content = message
            except queue.Empty:
                self._tick()
                continue
            self._status(agent_id, 'thinking', 'Demo: reading your message')
            if self._stop.wait(0.35):
                break
            name = next(a['name'] for a in self.agents if a['id'] == agent_id)
            self._publish(make_event(agent_id, 'message', message_id=str(uuid4()), role='assistant', content=(
                f'[DEMO - {name}] I received: "{content}"\n\n'
                'This is a simulated reply. Choose "Codex agents" under Activity source '
                "to start or resume this project's agents.")))
            self._status(agent_id, 'idle', 'Demo: replied to your message')

    def _tick(self):
        if not self.agents:
            return
        count = len(self.agents)
        index = self._step % count
        phase = (self._step // count) % 6
        agent = self.agents[index]
        agent_id = agent['id']
        self._step += 1
        states = [('thinking', 'Demo: planning the next change'), ('working', 'Demo: implementing assigned task'),
                  ('tool_call', 'Demo: inspecting project files'), ('working', 'Demo: reviewing implementation'),
                  ('waiting', 'Demo: waiting for a teammate'), ('idle', 'Demo: task complete')]
        if phase == 0 and agent_id == 'orchestrator' and count > 1:
            target = self.agents[(index + 1) % count]
            self._status(agent_id, 'working', 'Delegating to ' + target['name'])
            self._publish(make_event(agent_id, 'message', message_id=str(uuid4()), role='assistant',
                                    content=f"[DEMO delegation] Passing the task to {target['name']} ({target['id']})."))
            self._status(target['id'], 'working', 'Demo: received delegated task')
        elif phase == 2:
            tool = 'file' if index % 2 == 0 else 'shell'
            self._status(agent_id, 'tool_call', 'Demo: file inspection' if tool == 'file' else 'Demo: checking shell output')
            self._publish(make_event(agent_id, 'tool_call', tool=tool,
                                    name='Inspect project files' if tool == 'file' else 'Inspect command output', summary='Demo tool activity'))
        elif phase == 3 and (self._step // (count * 6)) % 2 == 0 and index == count - 1:
            self._status(agent_id, 'error', 'Demo: sample check failed')
            self._publish(make_event(agent_id, 'error', message='Simulated check failure', detail='Demo only; the next phase recovers.'))
        else:
            self._status(agent_id, *states[phase])
            if phase == 5:
                self._publish(make_event(agent_id, 'message', message_id=str(uuid4()), role='assistant',
                                        content='[DEMO] Work cycle complete; handed the result back for review.'))

    def send_message(self, agent_id, content):
        content = self._validate_message(agent_id, content)
        message_id = self._user_message(agent_id, content)
        self._messages.put((agent_id, content))
        return message_id

    def close(self):
        super().close()
        self._messages.put(None)
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
