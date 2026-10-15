"""Qt tabs, direct event-source bridge, and explicitly addressed conversations."""
from __future__ import annotations
from datetime import datetime
import html
import json
from pathlib import Path
from PySide6.QtCore import QObject, Qt, QTimer, Signal, QSignalBlocker, QUrl
from PySide6.QtGui import QIcon, QPixmap, QDesktopServices
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QTabWidget, QPushButton, QFrame, QTextBrowser, QPlainTextEdit, QComboBox, QFileDialog, QDialog, QMessageBox, QScrollArea
from sprites import PALETTE, ascii_text, whale_image
from ui.office import OfficeWidget
from ui.team import AddProjectDialog, TeamDialog

class EventBridge(QObject):
    received = Signal(object)

class MessageInput(QPlainTextEdit):
    submit = Signal()
    def __init__(self,parent=None):
        super().__init__(parent)
        self.placeholder=QLabel(self.viewport());self.placeholder.setObjectName('muted');self.placeholder.setStyleSheet('color: #A0AEC0; background: #1C2541;');self.placeholder.move(0,0);self.placeholder.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.textChanged.connect(lambda:self.placeholder.setVisible(not self.toPlainText()))
    def setPlaceholderText(self,text):
        self.placeholder.setText(str(text));self.placeholder.adjustSize();self.placeholder.setVisible(not self.toPlainText())
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            event.accept();self.submit.emit()
        else:super().keyPressEvent(event)

def label(value='',name=None):
    item=QLabel(str(value))
    item.setTextFormat(Qt.TextFormat.PlainText)
    if name:item.setObjectName(name)
    return item

def state_from(history):
    state={'status':'idle','summary':'Ready / waiting for activity'}
    for event in history:
        d=event.get('data',{});kind=event.get('type')
        if kind=='status_change':state.update(status=d.get('status','idle'),summary=d.get('summary',''))
        elif kind=='tool_call':state.update(status='tool_call',tool=d.get('tool','other'),summary=d.get('summary',d.get('name','Using a tool')))
        elif kind=='error':state.update(status='error',summary=d.get('message','Needs attention'))
        elif kind=='message' and d.get('role')=='assistant':state['summary']=d.get('content','').replace('\n',' ')
    return state

class AgentPanel(QWidget):
    send_requested=Signal(str,str)
    def __init__(self,agent,is_demo,parent=None,project_path=None):
        super().__init__(parent);self.project_path=Path(project_path or Path.cwd()).resolve();self.agent=agent;self.is_demo=is_demo;self.connection_status='DEMO' if is_demo else 'CONNECTING';self.events=[]
        layout=QVBoxLayout(self);layout.setContentsMargins(22,22,22,22);layout.setSpacing(14)
        header=QFrame();header.setObjectName('agentheader');row=QHBoxLayout(header);row.setContentsMargins(18,14,18,14)
        sprite=label();sprite.setPixmap(QPixmap.fromImage(whale_image(agent.get('species','blue_whale'))).scaled(128,64,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation));row.addWidget(sprite)
        info=QVBoxLayout();info.addWidget(label(agent['name'],'title'));role=label(agent.get('role',''),'muted');role.setWordWrap(True);info.addWidget(role)
        self.meta=label('', 'section');self.meta.setWordWrap(True);info.addWidget(self.meta);row.addLayout(info,1);layout.addWidget(header)
        logtitle=QHBoxLayout();logtitle.addWidget(label('ACTIVITY & CONVERSATION','section'));logtitle.addStretch();self.count=label('0 EVENTS','muted');logtitle.addWidget(self.count);layout.addLayout(logtitle)
        self.log=QTextBrowser();self.log.setOpenLinks(False);self.log.setAccessibleName(str(agent['name'])+' activity and conversation');layout.addWidget(self.log,1)
        self.problem=label('');self.problem.setStyleSheet('color: #E07A5F;');self.problem.setWordWrap(True);self.problem.hide();layout.addWidget(self.problem)
        composer_title=QHBoxLayout();composer_title.addWidget(label('MESSAGE '+agent['name'].upper(),'section'));composer_title.addStretch();self.references=QPushButton('Reference files...');self.references.setObjectName('secondary');self.references.clicked.connect(self.reference_files);composer_title.addWidget(self.references);layout.addLayout(composer_title)
        composer=QHBoxLayout();self.input=MessageInput();self.input.setPlaceholderText('Send an instruction or ask for an update...');self.input.setAccessibleName('Message '+str(agent['name']));self.input.setFixedHeight(84);self.input.submit.connect(self.submit)
        self.send=QPushButton('Send >');self.send.setMinimumHeight(84);self.send.clicked.connect(self.submit);composer.addWidget(self.input,1);composer.addWidget(self.send);layout.addLayout(composer)
        hint=QHBoxLayout();hint.addWidget(label('Enter to send / Shift+Enter for a new line','muted'));hint.addStretch();hint.addWidget(label('TO: '+agent['name']+' ONLY','section'));layout.addLayout(hint)
        self.update_status({'status':'idle'})
    def reference_files(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Choose files from this project',str(self.project_path),'All files (*)')
        if not paths:return
        relative=[]
        try:
            for raw in paths:
                resolved=Path(raw).resolve(strict=True)
                if not resolved.is_file():raise ValueError('Choose regular files inside the selected project.')
                relative.append(resolved.relative_to(self.project_path).as_posix())
        except (ValueError,OSError):
            QMessageBox.warning(self,'Choose files inside this project','Every reference must be a file inside '+str(self.project_path)+'. Links to files outside this folder are not accepted.');return
        section='Reference files:\n'+'\n'.join('- '+path for path in dict.fromkeys(relative))
        if self.input.toPlainText().strip():self.input.appendPlainText('\n'+section)
        else:self.input.setPlainText(section)
        self.input.setFocus()
    def submit(self):
        content=self.input.toPlainText().strip()
        if content:self.send_requested.emit(self.agent['id'],content)
    def accepted(self):self.input.clear();self.problem.hide();self.input.setFocus()
    def failed(self,message):self.problem.setText(str(message));self.problem.show()
    def update_status(self,state):
        self.meta.setText(str(f"{state.get('status','idle').upper().replace('_',' ')}  /  {self.agent.get('model','')}  /  {self.agent.get('reasoning_effort','medium')} effort  /  {self.connection_status}"))
    def render_history(self,events,force=False):
        self.events=events;bar=self.log.verticalScrollBar();near=bar.maximum()-bar.value()<65;old=bar.value();parts=[]
        colors={'user':PALETTE[6],'assistant':PALETTE[4],'tool_call':PALETTE[3],'status_change':PALETTE[13],'error':PALETTE[7]}
        titles={'user':'YOU > AGENT','assistant':'AGENT','tool_call':'TOOL CALL','status_change':'STATUS','error':'ERROR'}
        for event in events:
            d=event.get('data',{});kind=event.get('type','status_change');role=d.get('role','assistant') if kind=='message' else kind
            try:stamp=datetime.fromisoformat(event.get('timestamp','').replace('Z','+00:00')).astimezone().strftime('%H:%M:%S')
            except (ValueError,TypeError):stamp=''
            if kind=='message':content=d.get('content','')
            elif kind=='tool_call':content=' / '.join(dict.fromkeys(str(v) for v in (d.get('name'),d.get('summary')) if v))
            elif kind=='error':content='\n'.join(str(v) for v in (d.get('message'),d.get('detail')) if v)
            else:content=f"{d.get('status','idle').replace('_',' ')} / {d.get('summary','')}"
            content=html.escape(str(content)).replace('\n','<br>');title=html.escape(titles.get(role,'ACTIVITY'));color=colors.get(role,PALETTE[13]);text_color=PALETTE[7] if kind=='error' else PALETTE[13] if kind=='status_change' else PALETTE[14]
            parts.append(f'<p style="margin-top:14px;margin-bottom:5px;color:{color}">{title} / {stamp}</p><p style="margin-top:0px;margin-bottom:14px;line-height:150%;color:{text_color}">{content}</p><hr color="{PALETTE[2]}">')
        self.log.setHtml(''.join(parts) if parts else '<p style="color:#A0AEC0">Quiet waters. Send a message to get started.</p>');self.count.setText(f'{len(events)} EVENTS')
        if near or force:bar.setValue(bar.maximum())
        else:bar.setValue(old)

class MainWindow(QMainWindow):
    def __init__(self,source=None,project_dir=None,workspace=None):
        super().__init__();self.workspace=workspace;self._generation=0;self.unsubscribe=lambda:None;self.source=source;self.project_dir=Path(project_dir or Path(__file__).resolve().parents[1]);self.panels={};self.cards={};self.states={};self.histories={};self.roster=[];self.roster_signature=None;self._closed=False;self.live_connected=set()
        self.setWindowTitle('Mission Control / Underwater Agent Office');area=self.screen().availableGeometry();self.resize(min(1240,area.width()-40),min(1050,area.height()-60));self.setMinimumSize(760,620);self.setWindowIcon(QIcon(QPixmap.fromImage(whale_image('blue_whale'))))
        container=QWidget();self.setCentralWidget(container);layout=QVBoxLayout(container);layout.setContentsMargins(24,22,24,18);layout.setSpacing(16)
        masthead=QHBoxLayout();mast=QVBoxLayout();mast.setSpacing(8);mast.addWidget(label('MISSION CONTROL / LOCAL OPERATIONS','eyebrow'));mast.addWidget(label('Underwater Agent Office_','title'));mast.addWidget(label('A little below sea level. A lot getting done.','subtitle'));masthead.addLayout(mast,1);self.source_badge=label('', 'badge');self.source_badge.setToolTip(str(getattr(source,'config_warning','') or 'Event source is configured in config.json'));masthead.addWidget(self.source_badge);layout.addLayout(masthead)
        if self.workspace is not None:self.build_project_bar(layout)
        self.tabs=QTabWidget();self.tabs.setDocumentMode(True);self.tabs.setUsesScrollButtons(True);self.tabs.tabBar().setDrawBase(False);self.tabs.setAccessibleName('Office and agent tabs');layout.addWidget(self.tabs,1)
        self.office_page=QWidget();office_layout=QVBoxLayout(self.office_page);office_layout.setContentsMargins(16,14,16,14);office_layout.setSpacing(12)
        scenehead=QHBoxLayout();scenehead.addWidget(label('Office activity','section'));scenehead.addStretch();self.agent_count=label('','muted');scenehead.addWidget(self.agent_count);office_layout.addLayout(scenehead)
        self.office=OfficeWidget();self.office.agent_clicked.connect(self.open_agent);office_layout.addWidget(self.office,1)
        caption=QHBoxLayout();caption.addWidget(label('DEPTH 024 M / ALL SYSTEMS BELOW SEA LEVEL','section'));caption.addStretch();caption.addWidget(label('CLICK A WHALE TO CHECK IN','muted'));office_layout.addLayout(caption)
        self.card_host=QWidget();self.card_grid=QGridLayout(self.card_host);self.card_grid.setContentsMargins(0,0,0,0);self.card_grid.setSpacing(10);office_layout.addWidget(self.card_host)
        self.office_scroll=QScrollArea();self.office_scroll.setWidgetResizable(True);self.office_scroll.setWidget(self.office_page);self.tabs.addTab(self.office_scroll,'Office');self.tabs.currentChanged.connect(self.tab_changed)
        footer=QHBoxLayout();footer.addWidget(label('UNDERWATER OFFICE / v2.0','footer'));footer.addStretch();footer.addWidget(label('DESKTOP / YOUR CREW, YOUR CURRENT','footer'));layout.addLayout(footer)
        self.bridge=EventBridge(self);self.bridge.received.connect(self.dispatch_event,Qt.ConnectionType.QueuedConnection)
        self.attach_source(source if source is not None else self.workspace.create_source())
        self.roster_timer=QTimer(self);self.roster_timer.timeout.connect(self.refresh_roster);self.roster_timer.start(1000)
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
        self.project_path.setText('Working folder: '+project['path']);self.setWindowTitle(project['name']+' - Underwater Agent Office')
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
    def manage_team(self):
        dialog=TeamDialog(self.workspace,self,before_apply=self.confirm_connection_change);dialog.exec()
        if dialog.changed:
            try:self.restart_source()
            except Exception as exc:self.show_error(exc)
    def attach_source(self,source):
        self.source=source;self._generation+=1;token=self._generation;self.live_connected.clear();self.states.clear();self.histories.clear();self.roster_signature=None
        self.unsubscribe=source.subscribe(lambda event,generation=token:self.bridge.received.emit((generation,event)))
        self.refresh_roster();source.start();self.source_badge.setToolTip(str(getattr(source,'config_warning','') or 'Choose Demo activity or Codex agents in the activity source selector.'))
        if self.workspace is not None:self.sync_project_controls()
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
        selected=self.tabs.currentWidget();selected_id=getattr(selected,'agent',{}).get('id')
        self.roster_signature=signature;self.roster=roster
        while self.tabs.count()>1:
            widget=self.tabs.widget(1);self.tabs.removeTab(1);widget.deleteLater()
        self.panels={};self.cards={}
        while self.card_grid.count():
            item=self.card_grid.takeAt(0)
            if item.widget():item.widget().deleteLater()
        for i,agent in enumerate(roster):
            aid=agent['id'];events=list(self.source.history(aid));self.histories[aid]=events;self.states[aid]=state_from(events)
            for event in events:self.update_connection(event)
            panel=AgentPanel(agent,self.demo(aid),project_path=self.workspace.active_project['path'] if self.workspace is not None else self.project_dir);panel.send_requested.connect(self.send_message);panel.render_history(events);self.panels[aid]=panel
            self.tabs.addTab(panel,str(agent['name'])+(' [DEMO]' if panel.is_demo else ''))
            card=QPushButton();card.setObjectName('agentcard');card.setMinimumHeight(72);card.setIcon(QIcon(QPixmap.fromImage(whale_image(agent.get('species','blue_whale')))));from PySide6.QtCore import QSize
            card.setIconSize(QSize(64,32));card.clicked.connect(lambda checked=False,agent_id=aid:self.open_agent(agent_id));self.cards[aid]=card;self.card_grid.addWidget(card,i//4,i%4)
            self.update_agent(aid)
        self.office.set_roster(roster)
        for aid,state in self.states.items():self.office.set_state(aid,state)
        self.agent_count.setText(f'{len(roster)} AGENTS');self.update_source_badge()
        if selected_id:self.open_agent(selected_id)
    def update_connection(self,event):
        aid=event.get('agent_id');data=event.get('data',{});summary=str(data.get('summary','')).lower()
        if event.get('type')=='status_change':
            if 'live codex thread connected' in summary:self.live_connected.add(aid)
            elif data.get('status')=='waiting' and 'connect' in summary:self.live_connected.discard(aid)
    def connection_label(self,aid):
        return 'DEMO' if self.demo(aid) else 'LIVE' if aid in self.live_connected else 'CONNECTING'
    def update_source_badge(self):
        if self.source.mode=='mock':text='Demo activity / simulated'
        else:
            demos=sum(self.demo(a['id']) for a in self.roster);live=sum(self.connection_label(a['id'])=='LIVE' for a in self.roster);connecting=len(self.roster)-demos-live;text=f'CODEX / {live} LIVE / {connecting} CONNECTING / {demos} DEMO'
        self.source_badge.setText(text)
    def update_agent(self,aid):
        if aid not in self.panels:return
        panel=self.panels[aid];panel.is_demo=self.demo(aid);panel.connection_status=self.connection_label(aid);state=self.states.get(aid,{'status':'idle'});panel.update_status(state);i=self.tabs.indexOf(panel)
        self.tabs.setTabText(i,str(panel.agent['name'])+' ['+panel.connection_status+']')
        summary=str(state.get('summary','Waiting for activity'));summary=summary if len(summary)<=30 else summary[:27]+'...'
        self.cards[aid].setText(str(f"{panel.agent['name']}\n{state.get('status','idle').upper().replace('_',' ')} / {panel.connection_status}\n{summary}"));self.cards[aid].setToolTip(str(state.get('summary','')))
        self.office.set_state(aid,state)
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
    def save_screenshots(self,destination):
        destination=Path(destination);destination=destination if destination.suffix else destination.with_suffix('.png');destination.parent.mkdir(parents=True,exist_ok=True);self.office.frozen=True
        self.tabs.setCurrentIndex(0);from PySide6.QtWidgets import QApplication
        QApplication.processEvents();self.office.repaint();
        if not self.grab().save(str(destination)):raise OSError(f'Cannot save screenshot: {destination}')
        office_file=destination.with_name(destination.stem+'-office'+destination.suffix)
        if not self.grab().save(str(office_file)):raise OSError(f'Cannot save screenshot: {office_file}')
        paths=[destination,office_file]
        for agent in self.roster:
            self.open_agent(agent['id']);QApplication.processEvents();path=destination.with_name(destination.stem+'-'+agent['id']+destination.suffix)
            if not self.grab().save(str(path)):raise OSError(f'Cannot save screenshot: {path}')
            paths.append(path)
        self.tabs.setCurrentIndex(0)
        if self.workspace is not None:
            dialog=TeamDialog(self.workspace,self);dialog.show();QApplication.processEvents();path=destination.with_name(destination.stem+'-team'+destination.suffix)
            if not dialog.grab().save(str(path)):raise OSError(f'Cannot save screenshot: {path}')
            paths.append(path)
            for scroll in dialog.findChildren(QScrollArea):scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
            QApplication.processEvents();detail=destination.with_name(destination.stem+'-team-instructions'+destination.suffix)
            if not dialog.grab().save(str(detail)):raise OSError(f'Cannot save screenshot: {detail}')
            paths.append(detail);dialog.close()
        return paths
    def closeEvent(self,event):
        if not self._closed:
            self._closed=True;self._generation+=1;self.roster_timer.stop();self.office.timer.stop();self.unsubscribe();self.source.close()
        super().closeEvent(event)
