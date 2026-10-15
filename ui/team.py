"""Project creation and a human-readable editor for project-specific agent teams."""
from pathlib import Path
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox, QCheckBox, QPushButton, QLabel, QListWidget, QPlainTextEdit, QDialogButtonBox, QMessageBox, QInputDialog, QScrollArea, QWidget
from sprites import SPECIES, PALETTE

def text_label(text,wrap=False):
    item=QLabel(str(text));item.setTextFormat(Qt.TextFormat.PlainText);item.setWordWrap(wrap);item.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);return item

def error(parent,message):QMessageBox.warning(parent,'Please check these settings',str(message))

class AddProjectDialog(QDialog):
    def __init__(self,store,path,parent=None):
        super().__init__(parent);self.setWindowTitle('Add a project');self.resize(600,280);layout=QVBoxLayout(self);layout.setSpacing(16)
        layout.addWidget(text_label('Choose the team to copy into this project. Its agents, instructions, and conversations will be independent.',True));form=QFormLayout();self.name=QLineEdit(Path(path).name);form.addRow('Project name',self.name);self.path=QLineEdit(str(Path(path).resolve()));self.path.setReadOnly(True);form.addRow('Working folder',self.path);self.preset=QComboBox()
        for preset in store.presets:self.preset.addItem(preset['name']+(' (default)' if preset['id']==store.default_preset_id else ''),preset['id'])
        self.preset.setCurrentIndex(max(0,self.preset.findData(store.default_preset_id)));form.addRow('Team preset',self.preset);layout.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Add project');buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def accept(self):
        if not self.name.text().strip():error(self,'Give this project a name.');return
        super().accept()

class TeamDialog(QDialog):
    def __init__(self,store,parent=None,before_apply=None):
        super().__init__(parent);self.before_apply=before_apply or (lambda:True);self.store=store;self.project_id=store.active_project['id'];self.changed=False;self.current_id=None;self.loading=False;self._saved_form=None;self.setWindowTitle('Manage team - '+store.active_project['name']);area=self.screen().availableGeometry();self.resize(min(1060,area.width()-40),min(900,area.height()-60))
        outer=QVBoxLayout(self);outer.setContentsMargins(22,20,22,20);outer.setSpacing(14)
        intro=text_label('Each project owns its team and instruction files. Save a reusable preset when you want this team available for future projects.',True);intro.setObjectName('muted');outer.addWidget(intro)
        presets=QHBoxLayout();presets.addWidget(text_label('Team presets'));self.presets=QComboBox();presets.addWidget(self.presets,1);self.apply=QPushButton('Apply preset...');self.apply.setObjectName('secondary');self.apply.clicked.connect(self.apply_preset);presets.addWidget(self.apply);save_preset=QPushButton('Save team as preset...');save_preset.clicked.connect(self.save_preset);presets.addWidget(save_preset);outer.addLayout(presets)
        content=QHBoxLayout();left=QVBoxLayout();self.agent_list=QListWidget();self.agent_list.setMinimumWidth(220);self.agent_list.currentRowChanged.connect(self.select_agent);left.addWidget(self.agent_list,1);tools=QHBoxLayout();self.add=QPushButton('Add agent');self.add.clicked.connect(self.add_agent);tools.addWidget(self.add);self.remove=QPushButton('Remove');self.remove.setObjectName('secondary');self.remove.clicked.connect(self.remove_agent);tools.addWidget(self.remove);left.addLayout(tools);content.addLayout(left,1)
        right=QVBoxLayout();form=QFormLayout();form.setSpacing(10);self.agent_id=QLineEdit();self.agent_id.setPlaceholderText('Leave blank to generate a stable ID');form.addRow('Stable ID',self.agent_id);self.name=QLineEdit();form.addRow('Display name',self.name);self.role=QLineEdit();form.addRow('Role',self.role)
        self.model=QComboBox();self.model.setEditable(True);self.model.addItems(['gpt-6-astra','gpt-6.1-sol','gpt-6-sol','gpt-6-luna']);form.addRow('Model',self.model)
        self.effort=QComboBox();self.effort.setEditable(True);self.effort.addItems(['low','medium','high','xhigh','max','ultra']);self.effort.setCurrentText('medium');form.addRow('Reasoning effort',self.effort)
        self.species=QComboBox()
        for species in SPECIES:self.species.addItem(species.replace('_',' ').title(),species)
        form.addRow('Whale species',self.species);self.accent=QComboBox()
        names=['Deep ink','Midnight','Slate blue','Sea teal','Bright aqua','Warm paper','Sand','Coral','Warning red','Kelp','Leaf','Lime','Wood','Soft gray','Ice','White']
        for name,color in zip(names,PALETTE):self.accent.addItem(name+'  '+color,color)
        form.addRow('Accent color',self.accent);right.addLayout(form)
        right.addWidget(text_label('Agent instructions'));self.instructions=QPlainTextEdit();self.instructions.setAccessibleName('Agent instructions');self.instructions.setMinimumHeight(150);right.addWidget(self.instructions,1)
        self.instruction_path=text_label('',True);self.instruction_path.setObjectName('muted');right.addWidget(self.instruction_path);filetools=QHBoxLayout();self.open_file=QPushButton('Open instruction file');self.open_file.setObjectName('secondary');self.open_file.clicked.connect(self.open_instructions);filetools.addWidget(self.open_file);self.reload=QPushButton('Reload external edits');self.reload.setObjectName('secondary');self.reload.clicked.connect(self.reload_instructions);filetools.addWidget(self.reload);right.addLayout(filetools)
        notice=text_label('Changing the model, effort, role, or instructions starts a new conversation on the next Codex connection. Previous conversations remain in Codex. Name and appearance changes keep the current conversation.',True);notice.setObjectName('muted');right.addWidget(notice)
        actions=QHBoxLayout();self.fresh=QPushButton('New conversation...');self.fresh.setObjectName('secondary');self.fresh.clicked.connect(self.new_conversation);actions.addWidget(self.fresh);actions.addStretch();self.save=QPushButton('Save agent');self.save.clicked.connect(self.save_agent);right.addLayout(actions);editor=QWidget();editor.setLayout(right);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(editor);scroll.setMinimumWidth(440);content.addWidget(scroll,3);outer.addLayout(content,1)
        self.feedback=text_label('',True);self.feedback.setObjectName('section');outer.addWidget(self.feedback);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(self.reject);footer=QHBoxLayout();footer.addWidget(self.save);footer.addStretch();footer.addWidget(buttons);outer.addLayout(footer)
        self.refresh_presets();self.refresh_agents()
    def refresh_presets(self):
        self.presets.clear()
        for preset in self.store.presets:self.presets.addItem(preset['name']+(' (default)' if preset['id']==self.store.default_preset_id else ''),preset['id'])
    def refresh_agents(self,selected=None):
        self.loading=True;self.agents=self.store.list_agents(self.project_id);self.agent_list.clear()
        for agent in self.agents:self.agent_list.addItem(agent['name']+'\n'+agent.get('model',''))
        self.loading=False;index=next((i for i,a in enumerate(self.agents) if a['id']==selected),0);self.agent_list.setCurrentRow(index);self.select_agent(index);self.add.setEnabled(len(self.agents)<8);self.remove.setEnabled(len(self.agents)>1)
    def select_agent(self,index):
        if self.loading or not 0<=index<len(self.agents):return
        if not self.confirm_unsaved():
            previous=next((i for i,a in enumerate(self.agents) if a['id']==self.current_id),-1)
            self.agent_list.blockSignals(True);self.agent_list.setCurrentRow(previous);self.agent_list.blockSignals(False);return
        a=self.agents[index];self.current_id=a['id'];self.agent_id.setReadOnly(True);self.agent_id.setText(a['id']);self.name.setText(a['name']);self.role.setText(a.get('role',''));self.model.setCurrentText(a.get('model','gpt-6.1-sol'));self.effort.setCurrentText(a.get('reasoning_effort','medium'));self.species.setCurrentIndex(max(0,self.species.findData(a.get('species','blue_whale'))));self.accent.setCurrentIndex(max(0,self.accent.findData(a.get('accent_color','#5BC0BE'))));self.instructions.setPlainText(self.store.read_instructions(a['id'],self.project_id));self.instruction_path.setText(str(self.store.instructions_path(a['id'],self.project_id)));self.open_file.setEnabled(True);self.reload.setEnabled(True);self.fresh.setEnabled(True);self.remove.setEnabled(len(self.agents)>1);self.feedback.clear();self._saved_form=self.form_snapshot();self.instructions.document().setModified(False)
    def add_agent(self):
        if not self.confirm_unsaved():return
        self.agent_list.setCurrentRow(-1);self.current_id=None;self.agent_id.setReadOnly(False);self.agent_id.clear();self.name.clear();self.role.clear();self.model.setCurrentText('gpt-6.1-sol');self.effort.setCurrentText('medium');self.instructions.clear();self.instruction_path.setText('An instruction file is created when you save this agent.');self.open_file.setEnabled(False);self.reload.setEnabled(False);self.fresh.setEnabled(False);self.remove.setEnabled(False);self.name.setFocus();self.feedback.setText('New agent - complete the fields, then save.');self._saved_form=self.form_snapshot()
    def agent_values(self):
        base=next((dict(a) for a in self.agents if a['id']==self.current_id),{})
        base.update(name=self.name.text().strip(),role=self.role.text().strip(),model=self.model.currentText().strip(),reasoning_effort=self.effort.currentText().strip(),species=self.species.currentData(),accent_color=self.accent.currentData())
        aid=self.current_id or self.agent_id.text().strip()
        if aid:base['id']=aid
        return base
    def save_agent(self):
        if self.current_id is None and self.agent_id.text().strip().lower() in {a['id'] for a in self.agents}:
            error(self,'That stable ID already belongs to an agent. Choose a unique ID or leave it blank to generate one.');return False
        if not self.before_apply():return False
        try:saved=self.store.save_agent(self.agent_values(),self.instructions.toPlainText(),self.project_id)
        except Exception as exc:error(self,exc);return False
        self._saved_form=self.form_snapshot();self.changed=True;self.refresh_agents(saved['id']);self.feedback.setText('Agent saved. Changes take effect when you close this editor.');return True
    def remove_agent(self):
        if not self.current_id or not self.before_apply():return
        if QMessageBox.question(self,'Remove agent?','Remove this agent from this project? Other projects and existing Codex conversations are retained.')!=QMessageBox.StandardButton.Yes:return
        try:self.store.remove_agent(self.current_id,self.project_id)
        except Exception as exc:error(self,exc);return
        self._saved_form=None;self.changed=True;self.refresh_agents();self.feedback.setText('Agent removed from this project.')
    def open_instructions(self):
        if self.current_id:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.instructions_path(self.current_id,self.project_id))))
    def reload_instructions(self):
        if not self.current_id or not self.before_apply():return
        if self.instructions.document().isModified() and QMessageBox.question(self,'Reload instructions?','Replace the unsaved editor text with the instruction file on disk?')!=QMessageBox.StandardButton.Yes:return
        try:text=self.store.read_instructions(self.current_id,self.project_id);self.store.list_agents(self.project_id)
        except Exception as exc:error(self,exc);return
        self.instructions.setPlainText(text);self.instructions.document().setModified(False)
        if self._saved_form is not None:self._saved_form['instructions']=text
        self.changed=True;self.feedback.setText('External instructions reloaded. Behavior changes start a new conversation when this editor closes.')
    def new_conversation(self):
        if not self.current_id or not self.before_apply():return
        if QMessageBox.question(self,'Start a new conversation?','Start a new conversation for this agent on the next Codex connection? Its previous conversations remain in Codex.')!=QMessageBox.StandardButton.Yes:return
        try:self.store.reset_thread(self.current_id,self.project_id)
        except Exception as exc:error(self,exc);return
        self.changed=True;self.feedback.setText('New conversation requested. Close the editor to connect.')
    def save_preset(self):
        if not self.confirm_unsaved():return
        dialog=QDialog(self);dialog.setWindowTitle('Save reusable team preset');layout=QVBoxLayout(dialog);layout.addWidget(text_label('Copy the saved team and its instructions. Conversations and project paths are excluded.',True));name=QLineEdit();name.setPlaceholderText('For example: My coding crew');layout.addWidget(name);default=QCheckBox('Use as the default team for new projects');layout.addWidget(default);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        try:self.store.save_preset(name.text().strip(),self.project_id,make_default=default.isChecked())
        except Exception as exc:error(self,exc);return
        self.refresh_presets();self.feedback.setText('Reusable preset saved from the current saved team.')
    def apply_preset(self):
        preset_id=self.presets.currentData()
        if not preset_id or not self.confirm_unsaved() or not self.before_apply():return
        if QMessageBox.question(self,'Replace this project team?',f'Apply {self.presets.currentText()}? This replaces the selected project team and instructions and starts fresh conversations. Other projects and the preset are unchanged.')!=QMessageBox.StandardButton.Yes:return
        try:self.store.apply_preset(preset_id,self.project_id)
        except Exception as exc:error(self,exc);return
        self._saved_form=None;self.changed=True;self.refresh_agents();self.feedback.setText('Preset copied into this project. Close the editor to reconnect.')

    def form_snapshot(self):
        return {'id':self.agent_id.text(),'name':self.name.text(),'role':self.role.text(),'model':self.model.currentText(),'effort':self.effort.currentText(),'species':self.species.currentData(),'accent':self.accent.currentData(),'instructions':self.instructions.toPlainText()}
    def confirm_unsaved(self):
        if self._saved_form is None or self.form_snapshot()==self._saved_form:return True
        choice=QMessageBox.question(self,'Unsaved agent changes','Save your changes before continuing?',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Save)
        if choice==QMessageBox.StandardButton.Cancel:return False
        if choice==QMessageBox.StandardButton.Save:return self.save_agent()
        self.restore_form(self._saved_form);return True
    def restore_form(self,values):
        self.agent_id.setText(values['id']);self.name.setText(values['name']);self.role.setText(values['role']);self.model.setCurrentText(values['model']);self.effort.setCurrentText(values['effort']);self.species.setCurrentIndex(self.species.findData(values['species']));self.accent.setCurrentIndex(self.accent.findData(values['accent']));self.instructions.setPlainText(values['instructions'])
    def reject(self):
        if self.confirm_unsaved():super().reject()
    def closeEvent(self,event):
        if not self.confirm_unsaved():event.ignore();return
        super().closeEvent(event)
