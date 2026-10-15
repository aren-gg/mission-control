"""A nearest-neighbor QPainter office; everything is drawn from source."""
from __future__ import annotations
import math
import time
from PySide6.QtCore import Qt, QTimer, QRect, Signal, QSize
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QWidget
from sprites import COLORS, draw_whale, pixel_text, text_width, ascii_text

class OfficeWidget(QWidget):
    agent_clicked = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.roster=[];self.states={};self.positions={};self.hitboxes={};self.bubble_rects=[]
        self.epoch=time.monotonic();self.previous=self.epoch;self.frozen=False;self.scale_factor=1;self.image_origin=(0,0)
        self.setMinimumSize(480,270);self.setMouseTracking(True)
        self.setToolTip('Click a whale to open its agent tab. Agent tabs are also keyboard accessible.')
        self.timer=QTimer(self);self.timer.timeout.connect(self.update);self.timer.start(50)
    def sizeHint(self): return QSize(960,540)
    def set_roster(self, agents):
        self.roster=list(agents)
        for i,a in enumerate(self.roster):
            d=self.desk(i)
            if a['id'] not in self.positions:self.positions[a['id']]=[d[0]-33,d[1]-41]
        self.positions={a['id']:self.positions[a['id']] for a in self.roster}
        self.update()
    def desk(self,index):
        if len(self.roster)<=4:
            coords=((240,212),(100,157),(380,157),(240,105))
            return coords[index]
        # Up to eight desks use two rows. Labels fit inside every station.
        count=len(self.roster);cols=4;row=index//cols;col=index%cols
        return (68+col*114,125+row*105)
    def set_state(self,agent_id,state): self.states[agent_id]=state;self.update()
    def paintEvent(self,event):
        image=self.render_scene()
        scale=max(1,min(self.width()//480,self.height()//270));self.scale_factor=scale
        x=max(0,(self.width()-480*scale)//2);y=max(0,(self.height()-270*scale)//2);self.image_origin=(x,y)
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing,False);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False);p.fillRect(self.rect(),COLORS[1]);p.drawImage(QRect(x,y,480*scale,270*scale),image)
    def resizeEvent(self,event):
        # Keep a full integer-size scene; the surrounding Office scroll area handles shorter screens.
        target=max(1,self.width()//480)*270
        if self.minimumHeight()!=target:self.setMinimumHeight(target)
        super().resizeEvent(event)
    def mousePressEvent(self,event):
        x=(event.position().x()-self.image_origin[0])/self.scale_factor;y=(event.position().y()-self.image_origin[1])/self.scale_factor
        for agent_id,rect in reversed(list(self.hitboxes.items())):
            if rect.contains(round(x),round(y)):self.agent_clicked.emit(agent_id);return
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        x=(event.position().x()-self.image_origin[0])/self.scale_factor;y=(event.position().y()-self.image_origin[1])/self.scale_factor
        self.setCursor(Qt.CursorShape.PointingHandCursor if any(r.contains(round(x),round(y)) for r in self.hitboxes.values()) else Qt.CursorShape.ArrowCursor)
    def render_scene(self):
        now=time.monotonic();t=0 if self.frozen else now-self.epoch;dt=min(now-self.previous,.1);self.previous=now;frame=int(t*3)%2
        image=QImage(480,270,QImage.Format.Format_RGB32);image.fill(COLORS[1]);p=QPainter(image);p.setRenderHint(QPainter.RenderHint.Antialiasing,False);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False)
        def rect(x,y,w,h,col):p.fillRect(round(x),round(y),w,h,COLORS[col])
        rect(0,0,480,6,0);rect(0,6,480,2,2);rect(0,82,480,188,2);rect(0,83,480,2,0)
        for wx in (14,175,336):
            rect(wx,16,130,58,0);rect(wx+2,18,126,54,3);rect(wx+5,21,120,48,1);rect(wx+5,56,120,13,2);rect(wx+63,21,2,48,3);rect(wx+5,43,120,2,3)
            for k in range(4):
                by=24+int((k*11-t*3)%40);rect(wx+14+k*28,by,2,2,3)
            rect(wx+8,64,6,5,9);rect(wx+10,58,2,8,10);rect(wx+110,59,2,10,9)
        for y in range(98,266,24):
            rect(0,y,480,1,1)
            for x in range((y//24%2)*24,480,48):rect(x,y-12,1,12,1)
        for x in (66,226,386):rect(x,8,31,3,0);rect(x+3,11,25,2,6)
        # The title plaque sits on the central aquarium window.
        rect(181,13,116,27,1);pixel_text(p,'SUBSEA OPERATIONS',187,17,14);pixel_text(p,'EST. 2026 / 024 M',191,29,3)
        rect(5,157,31,39,0);rect(7,159,27,35,13)
        for y in (161,172,183):rect(9,y,23,9,2);rect(18,y+4,5,1,13)
        pixel_text(p,'FILES',8,200,14)
        rect(439,155,36,4,0);rect(441,159,3,29,12);rect(470,159,3,29,12);rect(443,132,27,23,0);rect(445,134,23,16,1);pixel_text(p,'>_',449,139,4);rect(454,151,5,4,13);pixel_text(p,'SHELL',441,193,14)
        rect(446,93,18,30,0);rect(449,86,12,13,3);rect(450,85,10,1,14);rect(448,100,14,21,14);rect(451,104,2,2,3);rect(457,104,2,2,7);rect(451,115,8,3,2)
        def plant(x,y):
            rect(x-5,y,12,7,12);rect(x-3,y+7,8,2,0);rect(x,y-19,2,19,10);rect(x-5,y-13,5,3,9);rect(x-5,y-18,2,5,10);rect(x+2,y-8,5,3,10);rect(x+5,y-14,2,6,9)
        plant(15,244);plant(463,244);plant(402,101)
        rect(47,248,2,8,7);rect(43,250,10,2,7);rect(44,246,2,5,7);rect(51,244,2,7,7)
        labels=[]
        any_error=any(self.states.get(a['id'],{}).get('status')=='error' for a in self.roster)
        for i,a in enumerate(self.roster):
            x,y=self.desk(i);species=a.get('species','blue_whale');s=self.states.get(a['id'],{})
            rect(x-32,y,66,4,0);rect(x-31,y+1,64,2,12);rect(x-29,y+4,3,15,12);rect(x+28,y+4,3,15,12)
            rect(x+3,y-22,24,20,0);rect(x+5,y-20,20,14,1);rect(x+8,y-17,12,1,8 if s.get('status')=='error' else 3);rect(x+8,y-13,7+frame*3,1,4);rect(x+13,y-2,4,2,13);rect(x-17,y-2,16,1,13)
            if species=='beluga':
                rect(x-27,y-17,23,16,0);rect(x-25,y-15,19,12,3);rect(x-25,y+5,2,12,12);rect(x-30,y+6,12,8,6);rect(x-28,y+8,5,2,7)
            if species=='orca':
                rect(x+36,y-26,15,43,0)
                for k in range(4):rect(x+38,y-24+k*10,11,8,1);rect(x+39,y-22+k*10,2,2,4 if k==int(t)%4 else 3)
            if species=='sperm_whale':
                rect(x-34,y-35,64,11,0)
                for k in range(3):rect(x-32+k*21,y-33,19,7,3);rect(x-30+k*21,y-30,11,1,4)
                rect(x+32,y-30,5,5,8 if any_error and frame else 3);rect(x+33,y-25,3,3,0)
            name=ascii_text(a['name']);label_x=max(2,min(478-text_width(name),x-text_width(name)//2));labels.append((name,label_x,y+23));
        self.hitboxes={};bubbles=[]
        for i,a in enumerate(self.roster):
            agent_id=a['id'];x,y=self.desk(i);s=self.states.get(agent_id,{});status=s.get('status','idle');summary=ascii_text(s.get('summary','Ready / waiting for activity'));pos=self.positions[agent_id];target=[x-32,y-40];delegate=None
            if a.get('species')=='blue_whale' and any(w in summary.lower() for w in ('delegat','handoff','assign')):
                delegate=next((b for b in self.roster if b['id']!=agent_id and (b['name'].lower() in summary.lower() or b['id'] in summary.lower())),None)
                if delegate:
                    dx,dy=self.desk(self.roster.index(delegate));target=[dx-70,dy-44]
            elif status in ('tool_call','waiting'):
                target=[400,156] if s.get('tool')=='shell' else [38,159]
            elif status=='idle':target[0]+=round(math.sin(t/4+i)*7)
            dx=target[0]-pos[0];dy=target[1]-pos[1];distance=math.hypot(dx,dy);moving=distance>2
            if moving and not self.frozen:
                speed=min(distance,dt*20);pos[0]+=dx/distance*speed;pos[1]+=dy/distance*speed
            bob=round(math.sin(t*1.7+i)*1.5);wx=round(pos[0]);wy=round(pos[1])+bob
            state='error' if status=='error' else 'walking' if moving else 'working' if status in ('working','thinking') else 'tool' if status in ('tool_call','waiting') else 'idle'
            draw_whale(p,a.get('species','blue_whale'),wx,wy,state,frame,moving and dx<0)
            self.hitboxes[agent_id]=QRect(wx-3,wy-3,70,38)
            for k in range(2):
                bx=wx+46+k*6;by=wy-3-int((t*8+k*9)%19);rect(bx,by,2,1,3);rect(bx-1,by+1,1,2,3);rect(bx+2,by+1,1,2,3);rect(bx,by+3,2,1,3)
            if status=='idle' and int(t)%9==0:rect(wx+44,wy+4,1,4,3);rect(wx+42,wy+3,5,1,3)
            if status=='error':rect(wx+56,wy-3,7,11,8);pixel_text(p,'!',wx+59,wy-1,15)
            if delegate:rect(wx+50,wy+22,8,10,0);rect(wx+51,wy+23,6,8,6);rect(wx+53,wy+21,2,2,13)
            if status=='working' and frame:rect(x-12,y-5,2,2,14);rect(x-6,y-4,2,2,14)
            label=summary if len(summary)<=36 else summary[:33]+'...';bubbles.append((label,wx+48,wy-18))
        # Reserve full name-label rows before placing speech balloons.
        occupied=[QRect(178,11,122,31)]+[QRect(lx-2,ly-1,text_width(name)+4,10) for name,lx,ly in labels]+[r.adjusted(3,3,-3,-3) for r in self.hitboxes.values()]
        self.bubble_rects=[]
        for label,anchor_x,anchor_y in bubbles:
            width=min(222,text_width(label)+10);bx=max(3,min(477-width,anchor_x-width//2));preferred=max(15,min(243,anchor_y));chosen=None
            candidates=[preferred]+list(range(preferred-16,12,-16))+list(range(preferred+16,245,16))
            for yy in candidates:
                candidate=QRect(bx,yy,width,14)
                if not any(candidate.adjusted(-2,-2,2,2).intersects(o) for o in occupied):chosen=candidate;break
            if chosen is None:
                for yy in range(14,244,15):
                    for xx in range(3,max(4,478-width),12):
                        candidate=QRect(xx,yy,width,14)
                        if not any(candidate.adjusted(-1,-1,1,1).intersects(o) for o in occupied):chosen=candidate;break
                    if chosen is not None:break
            if chosen is None:chosen=QRect(bx,preferred,width,14)
            occupied.append(chosen);self.bubble_rects.append(chosen)
            rect(chosen.x(),chosen.y(),width,14,0);rect(chosen.x()+1,chosen.y()+1,width-2,12,5);pixel_text(p,label,chosen.x()+5,chosen.y()+4,0)
            pointer_x=max(chosen.x()+3,min(chosen.right()-3,anchor_x));rect(pointer_x,chosen.bottom()+1,3,1,0);rect(pointer_x+1,chosen.bottom()+2,1,1,0)
        for name,lx,ly in labels:pixel_text(p,name,lx,ly,14)
        rect(0,260,480,10,0);pixel_text(p,'LOCAL OPERATIONS / OCEAN LINK',8,262,3);pixel_text(p,'024 M',443,262,3)
        p.end();return image
