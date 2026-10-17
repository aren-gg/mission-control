"""Always-accessible, project-aware setup instructions with direct app actions."""
import html
import json
from pathlib import Path
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QLabel, QTextBrowser, QPushButton, QWidget, QApplication

class SetupGuide(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.setWindowTitle('Setup Guide · Mission Control');area=self.screen().availableGeometry();self.resize(min(1000,area.width()-40),min(780,area.height()-60));self.setMinimumSize(700,540)
        outer=QVBoxLayout(self);outer.setContentsMargins(24,22,24,22);outer.setSpacing(16);title=QLabel('Setup Guide');title.setObjectName('title');outer.addWidget(title);self.context=QLabel();self.context.setWordWrap(True);self.context.setObjectName('muted');self.context.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);outer.addWidget(self.context)
        content=QHBoxLayout();self.steps=QListWidget();self.steps.setFixedWidth(200);self.steps.setWordWrap(True);self.steps.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.steps.addItems(['1  Choose a project','2  Install & sign in','3  Configure agents','4  Link teammates','5  Chats & handoffs','6  Advanced JSON','7  Reuse team presets']);self.steps.currentRowChanged.connect(self.render_step);content.addWidget(self.steps)
        page=QVBoxLayout();self.heading=QLabel();self.heading.setObjectName('title');self.heading.setWordWrap(True);page.addWidget(self.heading);self.body=QTextBrowser();self.body.setOpenExternalLinks(True);page.addWidget(self.body,1);self.actions=QVBoxLayout();self.actions.setSpacing(7);page.addLayout(self.actions);content.addLayout(page,1);outer.addLayout(content,1)
        nav=QHBoxLayout();self.back=QPushButton('Previous');self.back.setObjectName('secondary');self.back.clicked.connect(lambda:self.steps.setCurrentRow(self.steps.currentRow()-1));nav.addWidget(self.back);nav.addStretch();self.next=QPushButton('Next');self.next.clicked.connect(lambda:self.steps.setCurrentRow(self.steps.currentRow()+1));nav.addWidget(self.next);close=QPushButton('Close guide');close.setObjectName('secondary');close.clicked.connect(self.hide);nav.addWidget(close);outer.addLayout(nav);self.steps.setCurrentRow(0)
    def refresh(self):
        project=self.window.workspace.active_project if self.window.workspace is not None else {'name':self.window.project_dir.name,'path':str(self.window.project_dir)}
        self.context.setText(project['name']+'\n'+project['path']);self.render_step(max(0,self.steps.currentRow()))
    def add_action(self,text,callback,managed=False):
        button=QPushButton(text)
        if self.actions.count():button.setObjectName('secondary')
        button.clicked.connect(callback);button.setEnabled(not managed or self.window.workspace is not None);self.actions.addWidget(button)
    def render_step(self,index):
        if index<0:return
        while self.actions.count():
            item=self.actions.takeAt(0)
            if item.widget():item.widget().hide();item.widget().deleteLater()
        window=self.window;store=window.workspace;root=str(store.active_project['path']) if store else str(window.project_dir);escape=html.escape
        pages=[
          ('Choose the project you want to work on',f'<p>Team definitions are reusable. Conversations, instructions, and linked thread IDs belong to each project.</p><p>Use the project selector to switch workspaces, or choose <b>Add project</b> and pick a folder. Select a team preset to copy; later edits stay independent.</p><p><b>Selected working folder</b><br>{escape(root)}</p><p>Codex works in this folder. Demo activity only simulates messages. Choosing a folder does not confirm that Codex is installed or signed in.</p>'),
          ('Install Codex and sign in','<p>Mission Control connects to the local Codex CLI using its app-server. Install the CLI if needed, then sign in from Terminal.</p><p><b>Install</b><br><code>npm install -g @openai/codex</code></p><p><b>Sign in</b><br><code>codex login</code></p><p>Complete the authentication flow shown in Terminal. Then choose <b>Codex agents</b> in Activity source. Connection errors appear in each agent conversation.</p><p>This guide does not inspect your sign-in state. “Connected” appears only after the app-server confirms a thread connection.</p>'),
          ('Build a small, clear team','<p>Open <b>Manage team</b> to add or remove agents. Each agent needs a display name, a role, a model, reasoning effort, and instructions.</p><p>Keep responsibilities concrete: coordination, interface work, backend work, or review. The stable ID stays the same when you rename an agent.</p><p>The model dropdown also accepts a typed model name. Availability depends on your Codex account and installation; a saved value does not prove model access.</p><p><b>Save agent</b> persists edits. Changing behavior starts a new conversation on the next connection. Existing Codex conversations remain in Codex.</p>'),
          ('Choose who may delegate to whom','<p>In an agent’s settings, select its <b>Linked teammates</b>, then save. Links are directional: giving Orchestrator access to Backend does not automatically give Backend access to Orchestrator.</p><p>Each linked agent keeps a separate conversation. The handoff control lists only configured targets. Codex agents can also use the registered delegation tool for those linked targets.</p><p>Only grant links the agent needs. Linking is permission to route tasks; it does not merge chat histories or mean a task has run. Older attached conversations may lack the delegation tool. Choose New conversation in the agent settings to register it on a fresh Codex conversation.</p>'),
          ('Use direct messages or an explicit handoff','<p>Open any agent tab to chat with that agent independently. <b>Send message</b> sends the draft only to that agent.</p><p>To hand work to a teammate, write the task, select a linked target, and click <b>Hand off task</b>. Activity records the source, target, and result. A queued handoff is not a completed task.</p><p><b>Reference files</b> inserts project-relative paths in the draft. Files are not uploaded or read by that picker; Codex can read them while handling your task in the selected working folder.</p><p>To continue an existing Codex conversation, open the agent settings and use <b>Attach conversation</b> with its exact thread ID. Attach only a conversation appropriate for this project.</p>'),
          ('Edit files directly when you need to','<p>The form is the normal way to configure a team. Advanced users can open the selected project’s managed team JSON and instruction files in an external editor.</p><p>After saving external changes, use <b>Reload team JSON</b> or <b>Reload external edits</b>. JSON must validate before the app activates it. Unsaved form edits are guarded.</p><p>Configuration lives in Mission Control’s managed data directory, while agent work runs in the selected project folder.</p>'),
          ('Reuse a team without copying conversations','<p>In Manage team, choose <b>Save team as preset</b>, give the preset a name, and optionally make it the default for new projects.</p><p>Presets copy agent configuration, teammate links, and instruction text. They do not copy conversation IDs or another project’s paths.</p><p><b>Apply preset</b> replaces the selected project’s team after confirmation. Other projects and the preset stay independent.</p><p>There is no automatic “setup complete” badge: review the selected source and agent connection status, then send a small task to verify your actual workflow.</p>')]
        heading,body=pages[index]
        if index==5 and window.roster:
            first=window.roster[0];targets=[a['id'] for a in window.roster if a['id']!=first['id']][:2];example={'model':first.get('model','gpt-6.1-sol'),'reasoning_effort':first.get('reasoning_effort','medium'),'linked_agent_ids':targets}
            body+='<p><b>Example fields for agent '+escape(first['id'])+'</b></p><pre>'+escape(json.dumps(example,indent=2))+'</pre><p><b>model</b> chooses the model; <b>reasoning_effort</b> controls effort; <b>linked_agent_ids</b> lists stable IDs this agent may delegate to. Keep <b>id</b>, <b>instructions_file</b>, and internal fingerprint/generation fields unchanged. Use <b>Attach conversation</b> to change a thread ID safely.</p>'
        if index==5 and store is not None:
            try:
                body+=f'<p><b>Team JSON</b><br>{escape(str(store.roster_path()))}</p>'
                if window.roster:body+=f'<p><b>Example instruction file</b><br>{escape(str(store.instructions_path(window.roster[0]["id"])))}</p>'
            except (ValueError,OSError,KeyError) as error:
                body+='<p><b>Configuration needs attention.</b><br>'+escape(str(error))+'<br>Correct the external file, then use Reload team JSON to validate it.</p>'
        self.heading.setText(heading);self.body.setHtml('<style>p{line-height:155%;margin-bottom:16px}code{background:#EDF3F4;color:#236F73}</style>'+body);self.back.setEnabled(index>0);self.next.setEnabled(index<6)
        if index==0:self.add_action('Add project...',window.add_project,True);self.add_action('Open selected folder',window.open_project_folder,True)
        elif index==1:
            self.add_action('Copy install command',lambda:QApplication.clipboard().setText('npm install -g @openai/codex'));self.add_action('Copy sign-in command',lambda:QApplication.clipboard().setText('codex login'));self.add_action('CLI setup docs',lambda:QDesktopServices.openUrl(QUrl('https://learn.chatgpt.com/docs/codex/cli')))
        elif index in (2,3,6):self.add_action('Manage team...',window.manage_team,True)
        elif index==4:self.add_action('Open first conversation',self.open_first);self.add_action('Manage teammate links',window.manage_team,True)
        elif index==5:self.add_action('Open team JSON',window.open_team_json,True);self.add_action('Reload team JSON',window.reload_team_json,True);self.add_action('Open instruction settings',window.manage_team,True)
    def open_first(self):
        if self.window.roster:self.window.open_agent(self.window.roster[0]['id']);self.hide()
