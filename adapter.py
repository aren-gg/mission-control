"""Public source API for the desktop dashboard; no Qt dependency in this module."""
from __future__ import annotations
import json
import logging
import re
from pathlib import Path
from sources import AgentEventSource, MockEventSource, CodexAppServerSource, make_event

BASE_DIR = Path(__file__).resolve().parent
SPECIES = {'blue_whale', 'beluga', 'orca', 'sperm_whale', 'humpback', 'narwhal'}
PALETTE = {'#0B132B','#1C2541','#3A506B','#5BC0BE','#6FFFE9','#F4F1DE','#F2CC8F','#E07A5F',
           '#BC4749','#386641','#6A994E','#A7C957','#8D6E63','#A0AEC0','#DDEBF0','#FFFFFF'}


def load_roster(path=BASE_DIR / 'agents.json'):
    agents = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(agents, list) or not 1 <= len(agents) <= 8:
        raise ValueError('agents.json must contain an array of 1 to 8 agents')
    seen = set()
    seen_threads = set()
    for index, agent in enumerate(agents):
        prefix = f'agents.json entry {index + 1}'
        if not isinstance(agent, dict):
            raise ValueError(prefix + ' must be an object')
        agent_id = agent.get('id')
        if not isinstance(agent_id, str) or not re.fullmatch(r'[a-z][a-z0-9_-]*', agent_id):
            raise ValueError(prefix + ': id must be lowercase letters, numbers, underscores or hyphens')
        if agent_id in seen:
            raise ValueError(prefix + ': duplicate id ' + agent_id)
        seen.add(agent_id)
        for field in ('name', 'role', 'model'):
            if not isinstance(agent.get(field), str) or not agent[field].strip():
                raise ValueError(prefix + ': ' + field + ' must be nonempty text')
        if not isinstance(agent.get('species'), str) or agent['species'] not in SPECIES:
            raise ValueError(prefix + ': unsupported species')
        if not isinstance(agent.get('accent_color'), str) or agent['accent_color'] not in PALETTE:
            raise ValueError(prefix + ': accent_color must use the shared palette')
        thread_id = agent.get('app_server_thread_id')
        if thread_id is not None:
            if not isinstance(thread_id, str) or not thread_id.strip():
                raise ValueError(prefix + ': app_server_thread_id must be null or nonempty text')
            if thread_id in seen_threads:
                raise ValueError(prefix + ': each live agent must have a distinct thread ID')
            seen_threads.add(thread_id)
    return agents


def load_config(path=BASE_DIR / 'config.json'):
    try:
        config = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(config, dict) or config.get('source') not in ('mock', 'codex'):
            raise ValueError('config.json source must be mock or codex')
        command = config.get('app_server_command')
        if command is not None and (not isinstance(command, list) or not command
            or any(not isinstance(part, str) or not part for part in command)):
            raise ValueError('app_server_command must be a nonempty array of command arguments')
        return config
    except (OSError, ValueError, TypeError) as exc:
        logging.warning('Invalid settings; using DEMO mock source: %s', exc)
        return {'source': 'mock', 'warning': str(exc)}


def create_source(project_root=None):
    root = Path(project_root or BASE_DIR)
    agents = load_roster(root / 'agents.json')
    config = load_config(root / 'config.json')
    if config['source'] == 'codex':
        return CodexAppServerSource(agents, command=config.get('app_server_command'),
                                   project_root=root, roster_path=root / 'agents.json')
    source = MockEventSource(agents)
    source.config_warning = config.get('warning')
    return source


__all__ = ['AgentEventSource', 'MockEventSource', 'CodexAppServerSource', 'make_event', 'load_roster', 'load_config', 'create_source']
