"""Mission Control: project teams, independent conversations, and explicit handoffs."""
from __future__ import annotations
from datetime import datetime
import html
import json
from pathlib import Path
from PySide6.QtCore import QObject, Qt, QTimer, Signal, QSignalBlocker, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QTabWidget, QPushButton, QFrame, QTextBrowser, QPlainTextEdit, QComboBox, QFileDialog, QDialog, QMessageBox, QScrollArea
from ui.team import AddProjectDialog, TeamDialog

class EventBridge(QObject):
    received = Signal(object)

class MessageInput(QPlainTextEdit):
    submit = Signal()
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            event.accept();self.submit.emit()
        else:super().keyPressEvent(event)

def label(value='',name=None):
    item=QLabel(str(value));item.setTextFormat(Qt.TextFormat.PlainText)
    if name:item.setObjectName(name)
    return item

def state_from(history):
    state={'status':'idle','summary':'Ready for a conversation'}
    for event in history:
        d=event.get('data',{});kind=event.get('type')
        if kind=='status_change':state.update(status=d.get('status','idle'),summary=d.get('summary',''))
        elif kind=='tool_call':state.update(status='tool_call',tool=d.get('tool','other'),summary=d.get('summary',d.get('name','Using a tool')))
        elif kind=='error':state.update(status='error',summary=d.get('message','Needs attention'))
        elif kind=='message' and d.get('role')=='assistant':state['summary']=d.get('content','').replace('\n',' ')
    return state

class AgentCard(QFrame):
    def __init__(self,agent,roster,on_open,on_edit,parent=None):
        super().__init__(parent);self.setObjectName('agentcard');self.setMinimumWidth(270)
        box=QVBoxLayout(self);box.setContentsMargins(20,18,20,18);box.setSpacing(10)
        title=label(agent['name']);title.setWordWrap(True);title.setStyleSheet('font-size: 18px; font-weight: 600;');box.addWidget(title)
        role=label(agent.get('role',''),'muted');role.setWordWrap(True);box.addWidget(role)
        model=label(agent.get('model','')+' · '+agent.get('reasoning_effort','medium')+' effort','muted');model.setWordWrap(True);box.addWidget(model)
        self.status=label('','section');box.addWidget(self.status);self.summary=label('','muted');self.summary.setWordWrap(True);self.summary.setMinimumHeight(40);box.addWidget(self.summary)
        names={a['id']:a['name'] for a in roster};linked=[names.get(aid,aid) for aid in agent.get('linked_agent_ids',[])];links=label('Can delegate to: '+(', '.join(linked) if linked else 'No teammates linked'),'muted');links.setWordWrap(True);box.addWidget(links)
        row=QHBoxLayout();chat=QPushButton('Open conversation');chat.clicked.connect(lambda:on_open(agent['id']));row.addWidget(chat);edit=QPushButton('Settings');edit.setObjectName('secondary');edit.clicked.connect(lambda:on_edit(agent['id']));row.addWidget(edit);box.addLayout(row)
    def set_state(self,state,connection):
        self.status.setText(connection.title()+' · '+state.get('status','idle').replace('_',' ').capitalize());value=str(state.get('summary','Ready for a conversation'));self.summary.setText(value[:150]+('…' if len(value)>150 else ''));self.summary.setToolTip(value)

class AgentPanel(QWidget):
    send_requested=Signal(str,str)
    handoff_requested=Signal(str,str,str)
    def __init__(self,agent,is_demo,parent=None,project_path=None,roster=None):
        super().__init__(parent);self.project_path=Path(project_path or Path.cwd()).resolve();self.agent=agent;self.is_demo=is_demo;self.connection_status='DEMO' if is_demo else 'CONNECTING';self.events=[]
        layout=QVBoxLayout(self);layout.setContentsMargins(8,18,8,8);layout.setSpacing(14)
        header=QFrame();header.setObjectName('agentheader');info=QVBoxLayout(header);info.setContentsMargins(20,17,20,17);info.addWidget(label(agent['name'],'title'));role=label(agent.get('role',''),'muted');role.setWordWrap(True);info.addWidget(role);self.meta=label('','section');self.meta.setWordWrap(True);info.addWidget(self.meta);layout.addWidget(header)
        logtitle=QHBoxLayout();logtitle.addWidget(label('Conversation & activity','section'));logtitle.addStretch();self.count=label('0 events','muted');logtitle.addWidget(self.count);layout.addLayout(logtitle)
        self.log=QTextBrowser();self.log.setOpenLinks(False);self.log.setAccessibleName(agent['name']+' conversation');layout.addWidget(self.log,1)
        self.problem=label('');self.problem.setStyleSheet('color: #B24440;');self.problem.setWordWrap(True);self.problem.hide();layout.addWidget(self.problem)
        composer_title=QHBoxLayout();composer_title.addWidget(label('Message '+agent['name'],'section'));composer_title.addStretch();self.references=QPushButton('Reference files...');self.references.setObjectName('secondary');self.references.clicked.connect(self.reference_files);composer_title.addWidget(self.references);layout.addLayout(composer_title)
        composer=QHBoxLayout();self.input=MessageInput();self.input.setPlaceholderText('Describe a task or ask a question…');self.input.setAccessibleName('Message '+agent['name']);self.input.setFixedHeight(86);self.input.submit.connect(self.submit);self.send=QPushButton('Send message');self.send.clicked.connect(self.submit);composer.addWidget(self.input,1);composer.addWidget(self.send);layout.addLayout(composer)
        hint=label('Enter to send · Shift+Enter for a new line. Messages go only to '+agent['name']+'.','muted');hint.setWordWrap(True);layout.addWidget(hint)
        handoff=QHBoxLayout();handoff.addWidget(label('Delegate draft to','muted'));self.handoff_target=QComboBox();self.handoff_target.setAccessibleName('Linked teammate for handoff');names={a['id']:a['name'] for a in roster or []}
        for aid in agent.get('linked_agent_ids',[]):
            if aid!=agent['id']:self.handoff_target.addItem(names.get(aid,aid),aid)
        self.handoff=QPushButton('Hand off task');self.handoff.setObjectName('secondary');self.handoff.clicked.connect(self.delegate);handoff.addWidget(self.handoff_target,1);handoff.addWidget(self.handoff);layout.addLayout(handoff)
        self.handoff.setEnabled(self.handoff_target.count()>0);self.handoff_target.setEnabled(self.handoff_target.count()>0)
        if not self.handoff_target.count():self.handoff_target.addItem('Link teammates in Manage team')
        self.update_status({'status':'idle'})
    def delegate(self):
        target=self.handoff_target.currentData();content=self.input.toPlainText().strip()
        if not content:self.failed('Write the task in the message draft before handing it off.');return
        if target:self.handoff_requested.emit(self.agent['id'],target,content)
    def reference_files(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Choose files from this project',str(self.project_path),'All files (*)')
        if not paths:return
        relative=[]
        try:
            for raw in paths:
                resolved=Path(raw).resolve(strict=True)
                if not resolved.is_file():raise ValueError('Choose regular files inside the selected project.')
                relative.append(resolved.relative_to(self.project_path).as_posix())
        except (ValueError,OSError):QMessageBox.warning(self,'Choose files inside this project','Every reference must be a file inside '+str(self.project_path)+'. Links outside this folder are not accepted.');return
        section='Reference files:\n'+'\n'.join('- '+path for path in dict.fromkeys(relative))
        if self.input.toPlainText().strip():self.input.appendPlainText('\n'+section)
        else:self.input.setPlainText(section)
        self.input.setFocus()
    def submit(self):
        content=self.input.toPlainText().strip()
        if content:self.send_requested.emit(self.agent['id'],content)
    def accepted(self):self.input.clear();self.problem.hide();self.input.setFocus()
    def failed(self,message):self.problem.setText(str(message));self.problem.show()
    def update_status(self,state):self.meta.setText(f"{self.agent.get('model','')} · {self.agent.get('reasoning_effort','medium')} effort · {self.connection_status.title()} · {state.get('status','idle').replace('_',' ')}")
    def render_history(self,events,force=False):
        self.events=events;bar=self.log.verticalScrollBar();near=bar.maximum()-bar.value()<65;old=bar.value();parts=[]
        colors={'user':'#445C88','assistant':'#236F73','tool_call':'#697683','status_change':'#697683','error':'#B24440'};titles={'user':'You','assistant':self.agent['name'],'tool_call':'Tool','status_change':'Status','error':'Attention'}
        for event in events:
            d=event.get('data',{});kind=event.get('type','status_change');role=d.get('role','assistant') if kind=='message' else kind
            try:stamp=datetime.fromisoformat(event.get('timestamp','').replace('Z','+00:00')).astimezone().strftime('%H:%M:%S')
            except (ValueError,TypeError):stamp=''
            if kind=='message':content=d.get('content','')
            elif kind=='tool_call':content=' · '.join(dict.fromkeys(str(v) for v in (d.get('name'),d.get('summary')) if v))
            elif kind=='error':content='\n'.join(str(v) for v in (d.get('message'),d.get('detail')) if v)
            else:content=f"{d.get('status','idle').replace('_',' ')} · {d.get('summary','')}"
            content=html.escape(str(content)).replace('\n','<br>');title=html.escape(titles.get(role,'Activity'));color=colors.get(role,'#697683');text_color='#B24440' if kind=='error' else '#697683' if kind=='status_change' else '#243640'
            parts.append(f'<p style="margin-top:16px;margin-bottom:5px;color:{color};font-weight:600">{title} <span style="font-weight:400"> · {stamp}</span></p><p style="margin-top:0px;margin-bottom:16px;line-height:150%;color:{text_color}">{content}</p>')
        self.log.setHtml(''.join(parts) if parts else '<p style="color:#697683">This conversation is ready. Send a task to begin.</p>');self.count.setText(f'{len(events)} events')
        bar.setValue(bar.maximum() if near or force else old)

class MainWindow(QMainWindow):
    def __init__(self,source=None,project_dir=None,workspace=None):
        super().__init__();self.workspace=workspace;self._generation=0;self.unsubscribe=lambda:None;self.source=source;self.project_dir=Path(project_dir or Path(__file__).resolve().parents[1]);self.panels={};self.cards={};self.states={};self.histories={};self.roster=[];self.roster_signature=None;self._closed=False;self.live_connected=set();self.guide=None
        self.setWindowTitle('Mission Control');area=self.screen().availableGeometry();self.resize(min(1200,area.width()-40),min(920,area.height()-60));self.setMinimumSize(760,620)
        container=QWidget();self.setCentralWidget(container);layout=QVBoxLayout(container);layout.setContentsMargins(28,24,28,20);layout.setSpacing(18)
        masthead=QHBoxLayout();mast=QVBoxLayout();mast.setSpacing(5);mast.addWidget(label('PROJECT WORKSPACE','eyebrow'));mast.addWidget(label('Mission Control','title'));mast.addWidget(label('Your team, conversations, and next steps.','subtitle'));masthead.addLayout(mast,1);self.source_badge=label('','badge');masthead.addWidget(self.source_badge);guide=QPushButton('Setup Guide');guide.setObjectName('secondary');guide.clicked.connect(self.show_guide);masthead.addWidget(guide);layout.addLayout(masthead)
        if self.workspace is not None:self.build_project_bar(layout)
        self.tabs=QTabWidget();self.tabs.setDocumentMode(True);self.tabs.setUsesScrollButtons(True);self.tabs.tabBar().setDrawBase(False);self.tabs.setAccessibleName('Team overview and conversations');layout.addWidget(self.tabs,1)
        overview=QWidget();box=QVBoxLayout(overview);box.setContentsMargins(8,20,8,12);box.setSpacing(18)
        summary=QFrame();summary.setObjectName('summary');summarybox=QVBoxLayout(summary);summarybox.setContentsMargins(20,18,20,18);self.agent_count=label('','section');summarybox.addWidget(self.agent_count);self.next_step=label('','muted');self.next_step.setWordWrap(True);summarybox.addWidget(self.next_step);box.addWidget(summary)
        self.card_host=QWidget();self.card_grid=QGridLayout(self.card_host);self.card_grid.setContentsMargins(0,0,0,0);self.card_grid.setSpacing(16);box.addWidget(self.card_host);box.addStretch();self.overview_scroll=QScrollArea();self.overview_scroll.setWidgetResizable(True);self.overview_scroll.setWidget(overview);self.tabs.addTab(self.overview_scroll,'Team overview');self.tabs.currentChanged.connect(self.tab_changed)
        footer=QHBoxLayout();footer.addWidget(label('Mission Control · Local desktop workspace','footer'));footer.addStretch();layout.addLayout(footer)
        self.bridge=EventBridge(self);self.bridge.received.connect(self.dispatch_event,Qt.ConnectionType.QueuedConnection);self.attach_source(source if source is not None else self.workspace.create_source());self.roster_timer=QTimer(self);self.roster_timer.timeout.connect(self.refresh_roster);self.roster_timer.start(1000)
    def build_project_bar(self,layout):
        frame=QFrame();frame.setObjectName('projectbar');box=QVBoxLayout(frame);box.setContentsMargins(12,10,12,10);box.setSpacing(9)
        row=QHBoxLayout();row.addWidget(label('Project','section'));self.project_selector=QComboBox();self.project_selector.setAccessibleName('Project selector');self.project_selector.setMinimumWidth(220);self.project_selector.currentIndexChanged.connect(self.choose_project);row.addWidget(self.project_selector,1)
        self.add_project_button=QPushButton('Add project...');self.add_project_button.clicked.connect(self.add_project);row.addWidget(self.add_project_button);open_folder=QPushButton('Open folder');open_folder.setObjectName('secondary');open_folder.clicked.connect(self.open_project_folder);row.addWidget(open_folder);box.addLayout(row)
        row=QHBoxLayout();row.addWidget(label('Activity source','section'));self.source_selector=QComboBox();self.source_selector.addItem('Demo activity','mock');self.source_selector.addItem('Codex agents','codex');self.source_selector.currentIndexChanged.connect(self.choose_source);row.addWidget(self.source_selector);row.addStretch();self.manage_team_button=QPushButton('Manage team...');self.manage_team_button.clicked.connect(self.manage_team);row.addWidget(self.manage_team_button);box.addLayout(row)
        self.project_path=label('','muted');self.project_path.setWordWrap(True);self.project_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);box.addWidget(self.project_path);layout.addWidget(frame);self.sync_project_controls()
    def sync_project_controls(self):
        if self.workspace is None:return
        project=self.workspace.active_project
        with QSignalBlocker(self.project_selector):
            self.project_selector.clear()
            for item in self.workspace.projects:self.project_selector.addItem(item['name'],item['id'])
            self.project_selector.setCurrentIndex(self.project_selector.findData(project['id']))
        with QSignalBlocker(self.source_selector):self.source_selector.setCurrentIndex(max(0,self.source_selector.findData(project.get('source','mock'))))
        self.project_path.setText('Working folder: '+project['path']);self.setWindowTitle(project['name']+' · Mission Control')
    def show_error(self,message):QMessageBox.warning(self,'Could not complete the change',str(message))
    def choose_project(self,index):
        pid=self.project_selector.itemData(index)
        if not pid or pid==self.workspace.active_project['id']:return
        if not self.confirm_connection_change():self.sync_project_controls();return
        previous=self.workspace.active_project['id']
        try:self.workspace.select_project(pid);self.restart_source()
        except Exception as exc:
            self.workspace.select_project(previous);self.sync_project_controls();self.show_error(exc)
    def add_project(self):
        directory=QFileDialog.getExistingDirectory(self,'Choose the folder for your project',self.workspace.active_project['path'])
        if not directory:return
        dialog=AddProjectDialog(self.workspace,directory,self)
        if dialog.exec()!=QDialog.DialogCode.Accepted or not self.confirm_connection_change():return
        previous=self.workspace.active_project['id']
        try:
            project=self.workspace.add_project(dialog.name.text().strip(),directory,dialog.preset.currentData());self.workspace.select_project(project['id']);self.restart_source()
        except Exception as exc:
            self.workspace.select_project(previous);self.sync_project_controls();self.show_error(exc)
    def open_project_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.workspace.active_project['path']))
    def choose_source(self,index):
        mode=self.source_selector.itemData(index)
        if mode==self.workspace.active_project.get('source','mock'):return
        if not self.confirm_connection_change():self.sync_project_controls();return
        previous=self.workspace.active_project.get('source','mock')
        try:self.workspace.set_source(mode);self.restart_source()
        except Exception as exc:
            self.workspace.set_source(previous);self.sync_project_controls();self.show_error(exc)
    def confirm_connection_change(self):
        busy=[a['name'] for a in self.roster if not self.demo(a['id']) and self.states.get(a['id'],{}).get('status') in ('working','thinking','tool_call')]
        if not busy:return True
        return QMessageBox.question(self,'Live agents are working',', '.join(busy)+' are working. Reconnecting the project or team can interrupt their current work. Continue?')==QMessageBox.StandardButton.Yes
    def manage_team(self,agent_id=None):
        if self.workspace is None:self.show_error('Team settings require a managed workspace.');return
        try:dialog=TeamDialog(self.workspace,self,before_apply=self.confirm_connection_change)
        except (ValueError,OSError) as exc:self.show_error(exc);return
        if isinstance(agent_id,str):
            index=next((i for i,a in enumerate(dialog.agents) if a['id']==agent_id),0);dialog.agent_list.setCurrentRow(index)
        dialog.exec()
        if dialog.changed:
            try:self.restart_source()
            except Exception as exc:self.show_error(exc)
    def attach_source(self,source):
        self.source=source;self._generation+=1;token=self._generation;self.live_connected.clear();self.states.clear();self.histories.clear();self.roster_signature=None
        self.unsubscribe=source.subscribe(lambda event,generation=token:self.bridge.received.emit((generation,event)))
        self.refresh_roster();source.start();self.source_badge.setToolTip(str(getattr(source,'config_warning','') or 'Choose Demo activity or Codex agents in the activity source selector.'))
        if self.workspace is not None:self.sync_project_controls()
        if self.guide is not None:self.guide.refresh()
    def restart_source(self):
        # Validate the candidate without starting it. A failed load leaves the active source untouched.
        candidate=self.workspace.create_source()
        # Advance the generation before closing: queued callbacks from this source are stale.
        self._generation+=1;self.unsubscribe();self.source.close()
        self.attach_source(candidate)
    def dispatch_event(self,payload):
        if isinstance(payload,tuple) and len(payload)==2:
            generation,event=payload
            if generation!=self._generation:return
            self.on_event(event)
        else:self.on_event(payload)
    def demo(self,agent_id):return bool(self.source.is_demo(agent_id))
    def refresh_roster(self):
        roster=list(self.source.roster);signature=json.dumps(roster,sort_keys=True)
        if signature==self.roster_signature:return
        drafts={aid:(p.input.toPlainText(),p.handoff_target.currentData(),p.log.verticalScrollBar().value()) for aid,p in self.panels.items()} if self.roster_signature is not None else {}
        selected=self.tabs.currentWidget();selected_id=getattr(selected,'agent',{}).get('id');self.roster_signature=signature;self.roster=roster
        while self.tabs.count()>1:
            widget=self.tabs.widget(1);self.tabs.removeTab(1);widget.deleteLater()
        self.panels={};self.cards={}
        while self.card_grid.count():
            item=self.card_grid.takeAt(0)
            if item.widget():item.widget().deleteLater()
        for i,agent in enumerate(roster):
            aid=agent['id'];events=list(self.source.history(aid));self.histories[aid]=events;self.states[aid]=state_from(events)
            for event in events:self.update_connection(event)
            panel=AgentPanel(agent,self.demo(aid),project_path=self.workspace.active_project['path'] if self.workspace is not None else self.project_dir,roster=roster);panel.send_requested.connect(self.send_message);panel.handoff_requested.connect(self.delegate_message);panel.render_history(events)
            if aid in drafts:
                draft,target,scroll=drafts[aid];panel.input.setPlainText(draft);index=panel.handoff_target.findData(target)
                if index>=0:panel.handoff_target.setCurrentIndex(index)
                panel.log.verticalScrollBar().setValue(scroll)
            self.panels[aid]=panel;self.tabs.addTab(panel,agent['name'])
            card=AgentCard(agent,roster,self.open_agent,self.manage_team);self.cards[aid]=card;self.card_grid.addWidget(card,i//2,i%2);self.update_agent(aid)
        self.update_source_badge()
        if selected_id:self.open_agent(selected_id)
        if self.guide is not None:self.guide.refresh()
    def update_connection(self,event):
        aid=event.get('agent_id');data=event.get('data',{});summary=str(data.get('summary','')).lower()
        if event.get('type')=='status_change':
            if 'live codex thread connected' in summary:self.live_connected.add(aid)
            elif data.get('status')=='waiting' and 'connect' in summary:self.live_connected.discard(aid)
    def connection_label(self,aid):
        return 'DEMO' if self.demo(aid) else 'LIVE' if aid in self.live_connected else 'CONNECTING'
    def update_source_badge(self):
        demo_count=sum(self.demo(a['id']) for a in self.roster);live=sum(self.connection_label(a['id'])=='LIVE' for a in self.roster)
        self.source_badge.setText('Demo activity · simulated' if self.source.mode=='mock' else f'Codex · {live} connected · {demo_count} demo')
        linked=sum(len(a.get('linked_agent_ids',[])) for a in self.roster)
        self.agent_count.setText(f"{len(self.roster)} agents  ·  {linked} teammate links  ·  {live} connected")
        if self.source.mode=='mock':hint='Choose Codex agents in Activity source to connect. Demo activity is simulated and does not change project files.'
        elif live<len(self.roster)-demo_count:hint='Connecting configured agents. Open a conversation for connection updates and any required action.'
        elif not linked:hint='Link teammates in Manage team to enable delegation. Each agent also has its own conversation.'
        else:hint='Open a conversation to begin. Send a direct message or hand a task to a linked teammate.'
        self.next_step.setText(hint)
    def update_agent(self,aid):
        if aid not in self.panels:return
        panel=self.panels[aid];panel.is_demo=self.demo(aid);panel.connection_status=self.connection_label(aid);state=self.states.get(aid,{'status':'idle'});panel.update_status(state);i=self.tabs.indexOf(panel);self.tabs.setTabText(i,panel.agent['name']);self.tabs.setTabToolTip(i,panel.connection_status.title());self.cards[aid].set_state(state,panel.connection_status)
    def on_event(self,event):
        if self._closed or not isinstance(event,dict):return
        aid=event.get('agent_id');self.update_connection(event)
        if event.get('type')=='roster_update':self.refresh_roster();return
        if aid not in self.panels:return
        history=self.histories.setdefault(aid,[]);mid=event.get('data',{}).get('message_id') if event.get('type')=='message' else None
        if mid:
            index=next((i for i,e in enumerate(history) if e.get('type')=='message' and e.get('data',{}).get('message_id')==mid),None)
            if index is not None:history[index]=event
            else:history.append(event)
        elif not history or history[-1]!=event:history.append(event)
        if len(history)>2000:del history[:-2000]
        self.states[aid]=state_from(history);self.update_agent(aid);self.update_source_badge();self.panels[aid].render_history(history)
    def open_agent(self,agent_id):
        if agent_id in self.panels:self.tabs.setCurrentWidget(self.panels[agent_id])
    def tab_changed(self,index):
        widget=self.tabs.widget(index)
        if isinstance(widget,AgentPanel):widget.render_history(widget.events,True)
    def send_message(self,agent_id,content):
        panel=self.panels.get(agent_id)
        if panel is None:return
        try:self.source.send_message(agent_id,content)
        except Exception as error:panel.failed(str(error))
        else:panel.accepted()
    def delegate_message(self,from_id,to_id,content):
        panel=self.panels.get(from_id)
        if panel is None:return
        try:self.source.delegate_message(from_id,to_id,content)
        except Exception as error:panel.failed(error)
        else:panel.accepted()
    def show_guide(self):
        from ui.guide import SetupGuide
        if self.guide is None:self.guide=SetupGuide(self)
        self.guide.refresh();self.guide.show();self.guide.raise_();self.guide.activateWindow()
    def open_team_json(self):
        if self.workspace is not None:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.workspace.roster_path())))
    def reload_team_json(self):
        if self.workspace is None or not self.confirm_connection_change():return
        try:self.workspace.reload_project_config();self.restart_source()
        except Exception as exc:self.show_error(exc)
        else:QMessageBox.information(self,'Team configuration reloaded','The team JSON passed validation and is now active.')
    def save_screenshots(self,destination):
        from PySide6.QtWidgets import QApplication
        destination=Path(destination);destination=destination if destination.suffix else destination.with_suffix('.png');destination.parent.mkdir(parents=True,exist_ok=True);paths=[]
        def save(widget,suffix):
            path=destination if suffix is None else destination.with_name(destination.stem+'-'+suffix+destination.suffix)
            if not widget.grab().save(str(path)):raise OSError(f'Cannot save screenshot: {path}')
            paths.append(path)
        self.tabs.setCurrentIndex(0);QApplication.processEvents();save(self,None);save(self,'dashboard')
        for agent in self.roster:self.open_agent(agent['id']);QApplication.processEvents();save(self,agent['id'])
        self.tabs.setCurrentIndex(0)
        if self.workspace is not None:
            dialog=TeamDialog(self.workspace,self);dialog.show();QApplication.processEvents();save(dialog,'team')
            for scroll in dialog.findChildren(QScrollArea):scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
            QApplication.processEvents();save(dialog,'team-instructions');dialog.close()
        self.show_guide();QApplication.processEvents()
        for i in range(self.guide.steps.count()):self.guide.steps.setCurrentRow(i);QApplication.processEvents();save(self.guide,'guide-'+str(i+1))
        self.guide.hide();return paths
    def closeEvent(self,event):
        if not self._closed:
            self._closed=True;self._generation+=1;self.roster_timer.stop();self.unsubscribe();self.source.close()
        super().closeEvent(event)
