"""App-owned projects, team presets and editable instructions. No Qt dependency.

External project directories are working directories only. All configuration
writes remain below app_root/data; workspace.json is the atomic manifest.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
import re
import tempfile
import threading
import tomllib
from pathlib import Path
from uuid import uuid4

from adapter import BASE_DIR, load_config, validate_roster

EFFORTS = {'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'}
FIELDS = ('id', 'name', 'role', 'model', 'reasoning_effort', 'species', 'accent_color', 'linked_agent_ids')
LEGACY_ROLES = {'orchestrator': 'orchestrator.toml', 'frontend': 'frontend-implementor.toml',
                'backend': 'backend-implementor.toml', 'mission_control': 'mission-control.toml'}


def atomic_write(path, text):
    """Replace a UTF-8 file only after its complete content is flushed to disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path, value):
    atomic_write(path, json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def behavior_fingerprint(agent, instructions):
    behavior = {key: agent.get(key, 'medium' if key == 'reasoning_effort' else '')
                for key in ('model', 'reasoning_effort', 'role')}
    if agent.get('linked_agent_ids'):
        behavior['linked_agent_ids'] = sorted(agent['linked_agent_ids'])
    behavior['instructions'] = instructions
    return hashlib.sha256(json.dumps(behavior, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def default_team():
    rows = [
        ('orchestrator', 'Orchestrator', 'Coordinates implementation work', 'gpt-6-astra', 'blue_whale', '#5BC0BE', 'medium'),
        ('frontend', 'Front End', 'Builds the user interface', 'gpt-6.1-sol', 'beluga', '#DDEBF0', 'medium'),
        ('backend', 'Back End', 'Builds services and event sources', 'gpt-6.1-sol', 'orca', '#A0AEC0', 'medium'),
        ('mission_control', 'Mission Control', 'Checks progress and verifies delivery', 'gpt-6-luna', 'sperm_whale', '#3A506B', 'low'),
    ]
    return [dict(zip(('id', 'name', 'role', 'model', 'species', 'accent_color', 'reasoning_effort'), row)) for row in rows]


class WorkspaceStore:
    def __init__(self, app_root=None):
        self.app_root = Path(app_root or BASE_DIR).resolve()
        self.state_path = self.app_root / 'workspace.json'
        self.data_root = self.app_root / 'data'
        self._lock = threading.RLock()
        if self.state_path.exists():
            try:
                self._state = json.loads(self.state_path.read_text(encoding='utf-8'))
                self._validate_state()
            except (OSError, ValueError, TypeError, KeyError) as exc:
                raise ValueError(f'Cannot load {self.state_path}: {exc}. Keep a backup before repairing this file.') from exc
        else:
            self._migrate()

    def _managed(self, *parts):
        target = self.data_root.joinpath(*parts)
        root = self.data_root.resolve()
        resolved = target.resolve()
        # Prevent symlink escapes as well as ../ and absolute path traversal.
        if root != self.app_root / 'data' or not resolved.is_relative_to(root) or resolved != target.absolute():
            raise ValueError('Managed data path must remain inside the app data folder')
        return target

    def _validate_state(self):
        if not isinstance(self._state, dict) or self._state.get('version') != 1:
            raise ValueError('Unsupported workspace format')
        projects = self._state['projects']
        presets = self._state['presets']
        if not isinstance(projects, list) or not projects or not isinstance(presets, list) or not presets:
            raise ValueError('Workspace needs at least one project and preset')
        for group in (projects, presets):
            ids = set()
            for item in group:
                self._valid_id(item['id'])
                if item['id'] in ids:
                    raise ValueError('Duplicate workspace ID')
                ids.add(item['id'])
                if not isinstance(item.get('name'), str) or not item['name'].strip():
                    raise ValueError('Project/preset name cannot be blank')
        for project in projects:
            if not isinstance(project.get('path'), str) or not Path(project['path']).is_absolute():
                raise ValueError('Project paths must be absolute')
            if project.get('source') not in ('mock', 'codex'):
                raise ValueError('Project source must be mock or codex')
        if self._state.get('active_project_id') not in {p['id'] for p in projects}:
            raise ValueError('Active project is missing')
        if self._state.get('default_preset_id') not in {p['id'] for p in presets}:
            raise ValueError('Default preset is missing')

    @staticmethod
    def _valid_id(value):
        if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_-]*', value):
            raise ValueError('ID must start with a lowercase letter and use lowercase letters, digits, underscores or hyphens')
        return value

    def _persist(self):
        atomic_json(self.state_path, self._state)

    @property
    def projects(self):
        with self._lock:
            return copy.deepcopy(self._state['projects'])

    @property
    def presets(self):
        with self._lock:
            return copy.deepcopy(self._state['presets'])

    @property
    def active_project(self):
        return copy.deepcopy(self._project())

    @property
    def default_preset_id(self):
        return self._state['default_preset_id']

    def _project(self, project_id=None):
        project_id = project_id or self._state['active_project_id']
        for project in self._state['projects']:
            if project['id'] == project_id:
                return project
        raise ValueError('Unknown project: ' + str(project_id))

    def _preset(self, preset_id):
        for preset in self._state['presets']:
            if preset['id'] == preset_id:
                return preset
        raise ValueError('Unknown team preset: ' + str(preset_id))

    def _roster_path(self, project_id):
        return self._managed('projects', self._valid_id(project_id), 'agents.json')

    def _instruction_file(self, project_id, agent_id):
        return self._managed('projects', self._valid_id(project_id), 'instructions', self._valid_id(agent_id) + '.md')

    def _read_agents(self, project_id):
        path = self._roster_path(project_id)
        agents = json.loads(path.read_text(encoding='utf-8'))
        validate_roster(agents)
        changed = False
        candidate = []
        for agent in agents:
            self._valid_id(agent['id'])
            expected = 'instructions/' + agent['id'] + '.md'
            if agent.get('instructions_file', expected) != expected:
                raise ValueError('Instruction paths must use the managed file for that agent')
            self._assert_thread_unique(agent.get('app_server_thread_id'), project_id, agent['id'])
            text = self._instruction_file(project_id, agent['id']).read_text(encoding='utf-8')
            candidate.append((agent, text))
        # Complete validation/read phase first: a later invalid instruction path
        # must not cause partial resets or persistence of earlier entries.
        for agent, text in candidate:
            agent.setdefault('linked_agent_ids', [])
            if agent.get('delegation_tool_version') and self._state.get('dynamic_tool_threads', {}).get(agent.get('app_server_thread_id')) != {'project_id': project_id, 'agent_id': agent['id']}:
                agent.pop('delegation_tool_version', None)
                changed = True
            fingerprint = behavior_fingerprint(agent, text)
            if fingerprint != agent.get('behavior_fingerprint'):
                agent['app_server_thread_id'] = None
                agent.pop('delegation_tool_version', None)
                agent['behavior_fingerprint'] = fingerprint
                agent['thread_generation'] = uuid4().hex
                changed = True
        if changed:
            atomic_json(path, agents)
        return agents

    def _write_team(self, project_id, team, keep_threads=False):
        roster = []
        for template in team:
            agent = {field: copy.deepcopy(template[field]) for field in FIELDS if field in template}
            agent.setdefault('reasoning_effort', 'low' if agent['id'] == 'mission_control' else 'medium')
            instructions = template.get('instructions', '')
            if not isinstance(instructions, str):
                raise ValueError('Instructions must be text')
            agent['instructions_file'] = 'instructions/' + agent['id'] + '.md'
            agent['app_server_thread_id'] = template.get('app_server_thread_id') if keep_threads else None
            agent['behavior_fingerprint'] = behavior_fingerprint(agent, instructions)
            agent['thread_generation'] = uuid4().hex
            roster.append(agent)
        validate_roster(roster)
        for agent, template in zip(roster, team):
            atomic_write(self._instruction_file(project_id, agent['id']), template.get('instructions', ''))
        atomic_json(self._roster_path(project_id), roster)

    def _migrate(self):
        legacy_roster = self.app_root / 'agents.json'
        agents = json.loads(legacy_roster.read_text(encoding='utf-8')) if legacy_roster.is_file() else default_team()
        validate_roster(agents)
        team = []
        for old in agents:
            agent = copy.deepcopy(old)
            instructions = str(agent.pop('instructions', ''))
            role_file = LEGACY_ROLES.get(agent['id'], agent['id'] + '.toml')
            path = self.app_root / '.codex' / 'agents' / role_file
            if path.is_file():
                try:
                    role = tomllib.loads(path.read_text(encoding='utf-8'))
                except (OSError, ValueError) as exc:
                    raise ValueError(f'Cannot import agent instructions from {path}: {exc}') from exc
                instructions = role.get('developer_instructions', instructions)
                agent['model'] = role.get('model', agent['model'])
                agent.setdefault('reasoning_effort', role.get('model_reasoning_effort', 'medium'))
            agent.setdefault('reasoning_effort', 'low' if agent['id'] == 'mission_control' else 'medium')
            agent['instructions'] = instructions or f"{agent['role']}. Work within the selected project and report progress clearly."
            team.append(agent)
        project_id = 'project_' + uuid4().hex[:12]
        preset_id = 'preset_' + uuid4().hex[:12]
        config = load_config(self.app_root / 'config.json')
        project = {'id': project_id, 'name': self.app_root.name, 'path': str(self.app_root), 'source': config['source']}
        preset = {'id': preset_id, 'name': 'Default coding team', 'agents': self._clean_template(team)}
        self._state = {'version': 1, 'active_project_id': project_id, 'default_preset_id': preset_id,
                       'projects': [project], 'presets': [preset]}
        # Preserve legacy thread IDs only for this first imported project.
        self._write_team(project_id, team, keep_threads=True)
        self._persist()

    @staticmethod
    def _clean_template(team):
        return [{**{key: copy.deepcopy(agent[key]) for key in FIELDS if key in agent},
                 'instructions': agent.get('instructions', '')} for agent in team]

    def select_project(self, project_id):
        with self._lock:
            project = self._project(project_id)
            self._check_folder(project)
            self._state['active_project_id'] = project_id
            self._persist()
        return self.active_project

    @staticmethod
    def _check_folder(project):
        if not Path(project['path']).is_dir():
            raise ValueError('Project folder is unavailable: ' + project['path'] + '. Restore it or select a different project.')

    def add_project(self, name, path, preset_id=None):
        with self._lock:
            if not isinstance(name, str) or not name.strip():
                raise ValueError('Give the project a name')
            if path is None or (isinstance(path, str) and not path.strip()):
                raise ValueError('Choose an existing project folder; the path cannot be blank')
            folder = Path(path).expanduser().resolve()
            if not folder.is_dir():
                raise ValueError('Choose an existing project folder')
            if any(Path(p['path']) == folder for p in self._state['projects']):
                raise ValueError('That project folder is already registered; select it from the project list')
            template = self._preset(preset_id or self.default_preset_id)
            project = {'id': 'project_' + uuid4().hex[:12], 'name': name.strip(), 'path': str(folder), 'source': 'mock'}
            self._write_team(project['id'], copy.deepcopy(template['agents']))
            self._state['projects'].append(project)
            self._persist()
            return copy.deepcopy(project)

    def set_source(self, mode, project_id=None):
        if mode not in ('mock', 'codex'):
            raise ValueError('Choose mock or codex as the event source')
        with self._lock:
            project = self._project(project_id)
            project['source'] = mode
            self._persist()
            return copy.deepcopy(project)

    def list_agents(self, project_id=None):
        with self._lock:
            return copy.deepcopy(self._read_agents(self._project(project_id)['id']))

    def instructions_path(self, agent_id, project_id=None):
        with self._lock:
            project = self._project(project_id)
            self._valid_id(agent_id)
            # Pure path lookup remains useful while the user repairs an invalid
            # advanced roster edit. Do not commit derived fingerprint updates.
            roster = json.loads(self._roster_path(project['id']).read_text(encoding='utf-8'))
            if not isinstance(roster, list) or not any(isinstance(a, dict) and a.get('id') == agent_id for a in roster):
                raise ValueError('Unknown agent: ' + str(agent_id))
            return self._instruction_file(project['id'], agent_id)

    def read_instructions(self, agent_id, project_id=None):
        return self.instructions_path(agent_id, project_id).read_text(encoding='utf-8')

    def save_agent(self, agent, instructions, project_id=None):
        if not isinstance(agent, dict) or not isinstance(instructions, str):
            raise ValueError('Agent settings must be an object and instructions must be text')
        with self._lock:
            project = self._project(project_id)
            roster = self._read_agents(project['id'])
            agent_id = agent.get('id') or 'agent_' + uuid4().hex[:12]
            self._valid_id(agent_id)
            old = next((a for a in roster if a['id'] == agent_id), None)
            if old is None and len(roster) >= 8:
                raise ValueError('A project can contain at most 8 agents')
            saved = {field: copy.deepcopy(agent[field]) for field in FIELDS if field in agent}
            saved['id'] = agent_id
            if agent.get('instructions_file') not in (None, 'instructions/' + agent_id + '.md'):
                raise ValueError('Instruction paths must use the managed file for that agent')
            saved.setdefault('reasoning_effort', 'medium')
            saved.setdefault('linked_agent_ids', copy.deepcopy(old.get('linked_agent_ids', [])) if old else [])
            if not isinstance(saved['reasoning_effort'], str) or saved['reasoning_effort'] not in EFFORTS:
                raise ValueError('Unsupported reasoning effort; use low, medium, high, xhigh, max, ultra, minimal or none')
            saved['instructions_file'] = 'instructions/' + agent_id + '.md'
            saved['behavior_fingerprint'] = behavior_fingerprint(saved, instructions)
            same_behavior = old and old['behavior_fingerprint'] == saved['behavior_fingerprint']
            saved['app_server_thread_id'] = old.get('app_server_thread_id') if same_behavior else None
            saved['thread_generation'] = old.get('thread_generation') if same_behavior else uuid4().hex
            if same_behavior and old.get('delegation_tool_version'):
                saved['delegation_tool_version'] = old['delegation_tool_version']
            updated = [saved if a['id'] == agent_id else a for a in roster]
            if old is None:
                updated.append(saved)
            validate_roster(updated)
            atomic_write(self._instruction_file(project['id'], agent_id), instructions)
            atomic_json(self._roster_path(project['id']), updated)
            return copy.deepcopy(saved)

    def remove_agent(self, agent_id, project_id=None):
        with self._lock:
            project = self._project(project_id)
            roster = self._read_agents(project['id'])
            if not any(a['id'] == agent_id for a in roster):
                raise ValueError('Unknown agent: ' + str(agent_id))
            if len(roster) <= 1:
                raise ValueError('Keep at least one agent in the project')
            cleaned = [a for a in roster if a['id'] != agent_id]
            for agent in cleaned:
                if agent_id in agent.get('linked_agent_ids', []):
                    agent['linked_agent_ids'] = [target for target in agent['linked_agent_ids'] if target != agent_id]
                    agent['app_server_thread_id'] = None
                    agent.pop('delegation_tool_version', None)
                    agent['thread_generation'] = uuid4().hex
                    text = self._instruction_file(project['id'], agent['id']).read_text(encoding='utf-8')
                    agent['behavior_fingerprint'] = behavior_fingerprint(agent, text)
            validate_roster(cleaned)
            atomic_json(self._roster_path(project['id']), cleaned)
            # Keep its instructions on disk as a recoverable local record.

    def save_preset(self, name, project_id=None, make_default=False):
        if not isinstance(name, str) or not name.strip():
            raise ValueError('Give the team preset a name')
        with self._lock:
            if any(p['name'].casefold() == name.strip().casefold() for p in self._state['presets']):
                raise ValueError('A team preset already has that name; choose another name')
            project = self._project(project_id)
            team = self._read_agents(project['id'])
            for agent in team:
                agent['instructions'] = self._instruction_file(project['id'], agent['id']).read_text(encoding='utf-8')
            preset = {'id': 'preset_' + uuid4().hex[:12], 'name': name.strip(), 'agents': self._clean_template(team)}
            self._state['presets'].append(preset)
            if make_default:
                self._state['default_preset_id'] = preset['id']
            self._persist()
            return copy.deepcopy(preset)

    def apply_preset(self, preset_id, project_id=None):
        with self._lock:
            project = self._project(project_id)
            preset = self._preset(preset_id)
            self._write_team(project['id'], copy.deepcopy(preset['agents']))
            return self.list_agents(project['id'])

    def reset_thread(self, agent_id, project_id=None):
        with self._lock:
            project = self._project(project_id)
            roster = self._read_agents(project['id'])
            agent = next((a for a in roster if a['id'] == agent_id), None)
            if agent is None:
                raise ValueError('Unknown agent: ' + str(agent_id))
            agent['app_server_thread_id'] = None
            agent.pop('delegation_tool_version', None)
            # A generation guards against a stale source restoring the old mapping.
            agent['thread_generation'] = uuid4().hex
            atomic_json(self._roster_path(project['id']), roster)

    def roster_path(self, project_id=None):
        with self._lock:
            return self._roster_path(self._project(project_id)['id'])

    def reload_project_config(self, project_id=None):
        with self._lock:
            pid = self._project(project_id)['id']
            # Candidate validation precedes _read_agents' fingerprint commit.
            roster = json.loads(self._roster_path(pid).read_text(encoding='utf-8'))
            validate_roster(roster)
            for agent in roster:
                self._assert_thread_unique(agent.get('app_server_thread_id'), pid, agent['id'])
            return copy.deepcopy(self._read_agents(pid))

    def _assert_thread_unique(self, thread_id, project_id, agent_id):
        if not thread_id:
            return
        for project in self._state['projects']:
            roster = json.loads(self._roster_path(project['id']).read_text(encoding='utf-8'))
            for agent in roster:
                if project['id'] == project_id and agent['id'] == agent_id:
                    continue
                if agent.get('app_server_thread_id') == thread_id:
                    raise ValueError('That conversation is already attached to another agent in this workspace')

    def link_existing_thread(self, agent_id, thread_id, project_id=None):
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError('Enter a nonempty Codex conversation ID')
        thread_id = thread_id.strip()
        with self._lock:
            project = self._project(project_id)
            roster = self._read_agents(project['id'])
            agent = next((a for a in roster if a['id'] == agent_id), None)
            if agent is None:
                raise ValueError('Unknown agent: ' + str(agent_id))
            self._assert_thread_unique(thread_id, project['id'], agent_id)
            agent['app_server_thread_id'] = thread_id
            agent.pop('delegation_tool_version', None)
            agent['thread_generation'] = uuid4().hex
            validate_roster(roster)
            atomic_json(self._roster_path(project['id']), roster)
            return copy.deepcopy(agent)

    def _save_thread(self, project_id, snapshot, thread_id):
        with self._lock:
            roster = self._read_agents(project_id)
            current = next((a for a in roster if a['id'] == snapshot['id']), None)
            if current is None or current['behavior_fingerprint'] != snapshot.get('behavior_fingerprint') or current.get('thread_generation') != snapshot.get('thread_generation') or current.get('app_server_thread_id') not in (None, snapshot.get('app_server_thread_id')):
                raise ValueError('Agent settings changed; discarded a stale thread mapping')
            self._assert_thread_unique(thread_id, project_id, current['id'])
            current['app_server_thread_id'] = thread_id
            current['delegation_tool_version'] = 1
            self._state.setdefault('dynamic_tool_threads', {})[thread_id] = {'project_id': project_id, 'agent_id': current['id']}
            validate_roster(roster)
            atomic_json(self._roster_path(project_id), roster)
            self._persist()

    def create_source(self, project_id=None):
        from adapter import create_source
        with self._lock:
            project = copy.deepcopy(self._project(project_id))
            self._check_folder(project)
            roster = self._read_agents(project['id'])
            instructions = {a['id']: self._instruction_file(project['id'], a['id']).read_text(encoding='utf-8') for a in roster}
            config = load_config(self.app_root / 'config.json')
            config['source'] = project['source']
            snapshots = {a['id']: copy.deepcopy(a) for a in roster}
            return create_source(project_root=Path(project['path']), agents=roster, config=config,
                roster_path=self._roster_path(project['id']), instructions=instructions,
                thread_saver=lambda agent_id, thread_id: self._save_thread(project['id'], snapshots[agent_id], thread_id))
