"""Click-through overlay, visible only over the foreground MuMu window."""
import time,logging,ctypes as C
from ctypes import wintypes as W
import numpy as np
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt,QTimer,QRectF,QVariantAnimation,QEasingCurve
from PySide6.QtGui import QPainter,QColor,QFont,QImage,QGuiApplication
from .vision import board_rect
from .presentation import OVERLAY_OPACITY,markers_and_recommendations,probability_fill
from PySide6.QtSvg import QSvgRenderer
from autotata.paths import ASSETS

class Overlay(QWidget):
    def __init__(self):
        super().__init__(None,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.WindowTransparentForInput|Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground);self.setAttribute(Qt.WA_TransparentForMouseEvents);self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.chest=QSvgRenderer(str(ASSETS/'ui/treasure-chest.svg'))
        self.target=None;self.active=False;self.updated=0;self.data={};self.mapping=None;self.geometry_key=None
        self.display_probabilities=[];self.number_from=[];self.number_to=[]
        self.number_animation=QVariantAnimation(self);self.number_animation.setDuration(220)
        self.number_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.number_animation.valueChanged.connect(self.animate_numbers)
        self.timer=QTimer(self);self.timer.setInterval(200);self.timer.timeout.connect(self.track);self.timer.start()
    def bind(self,hwnd):self.target=hwnd;self.mapping=None;self.geometry_key=None
    def publish(self,data):
        old=self.data
        values=list(data.get('probabilities',[]))
        start=self.display_probabilities if len(self.display_probabilities)==len(values) else old.get('probabilities',[])
        same_board=old.get('size')==data.get('size') and tuple(old.get('rect',()))==tuple(data.get('rect',()))
        self.number_animation.stop();self.data=data
        self.number_to=values
        self.number_from=[a if same_board and i<len(old.get('cells',[])) and old['cells'][i]==0 and i<len(data.get('cells',[])) and data['cells'][i]==0 and a is not None and b is not None else b for i,(a,b) in enumerate(zip(start,values))] if len(start)==len(values) else values[:]
        self.display_probabilities=self.number_from[:]
        if same_board and self.number_from!=self.number_to:
            self.number_animation.setStartValue(0.0);self.number_animation.setEndValue(1.0);self.number_animation.start()
        else:self.display_probabilities=values[:]
        self.update()
    def animate_numbers(self,progress):
        self.display_probabilities=[a+(b-a)*progress if a is not None and b is not None else b for a,b in zip(self.number_from,self.number_to)]
        self.update()
    def heartbeat(self):self.updated=time.monotonic()
    def setEnabled(self,value):
        self.active=bool(value)
        if not self.timer.isActive():self.timer.start()
        self.track()
    def hidden(self,reason):
        if getattr(self,'visibility_reason',None)!=reason:
            logging.getLogger('treasure.overlay').info('Overlay hidden: %s',reason)
        self.visibility_reason=reason;self.hide()
    def track(self):
        if not self.active:self.hidden('disabled');return
        if not self.data:self.hidden('no result');return
        if not self.target:self.hidden('no target');return
        if time.monotonic()-self.updated>10:self.hidden('no recent board');return
        from fishing.windows import user32,client_rect,api
        hwnd=self.target
        if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd) or user32.GetAncestor(user32.GetForegroundWindow(),2)!=user32.GetAncestor(hwnd,2):
            self.hidden('MuMu not foreground or minimized');return
        try:
            x,y,w,h=client_rect(hwnd)
            # Monitor-aware physical-pixel to Qt logical coordinate conversion.
            class Info(C.Structure):_fields_=[('cbSize',W.DWORD),('monitor',W.RECT),('work',W.RECT),('flags',W.DWORD),('device',W.WCHAR*32)]
            monitor=api(user32,'MonitorFromWindow',[W.HWND,W.DWORD],W.HANDLE)(hwnd,2)
            info=Info();info.cbSize=C.sizeof(info)
            api(user32,'GetMonitorInfoW',[W.HANDLE,C.c_void_p],W.BOOL)(monitor,C.byref(info))
            screen=next((s for s in QGuiApplication.screens() if s.name()==info.device),QGuiApplication.primaryScreen())
            dpr=screen.devicePixelRatio();origin=screen.geometry().topLeft()
            key=(w,h,dpr,self.data.get('size'))
            if key!=self.geometry_key:
                self.hide()
                if getattr(self,'pending_key',None)!=key:
                    self.pending_key=key;return
                pix=screen.grabWindow(0);im=pix.toImage().convertToFormat(QImage.Format_RGB888).copy(x-info.monitor.left,y-info.monitor.top,w,h)
                arr=np.frombuffer(im.bits(),np.uint8).reshape(im.height(),im.bytesPerLine())[:,:im.width()*3].reshape(im.height(),im.width(),3)[:,:,::-1].copy()
                found=board_rect(arr)
                if found is None or found[1]!=self.data.get('size'):
                    self.hidden('waiting for screen board mapping');return
                # Reject unknown Qt capture framing instead of shifting the overlay.
                if abs(im.width()-w)>3 or abs(im.height()-h)>3:return
                self.mapping=found[0];self.geometry_key=key
            bx,by,bw,bh=self.mapping
            self.setGeometry(round(origin.x()+(x+bx-info.monitor.left)/dpr),round(origin.y()+(y+by-info.monitor.top)/dpr),round(bw/dpr),round(bh/dpr))
            if getattr(self,'visibility_reason',None)!='visible':logging.getLogger('treasure.overlay').info('Overlay visible: %s',self.geometry().getRect())
            self.visibility_reason='visible';self.show();self.update()
        except (RuntimeError,ValueError) as exc:self.hidden(str(exc))
    def paintEvent(self,event):
        p=QPainter(self);p.setOpacity(OVERLAY_OPACITY);p.setRenderHint(QPainter.Antialiasing);n=self.data.get('size',0)
        if not n:return
        cw=self.width()/n;ch=self.height()/n
        probabilities=self.data.get('probabilities',[]);cells=self.data.get('cells',[])
        certain=set(self.data.get('certainTreasure',[]))
        candidates=set(self.data.get('candidateTreasure',[]))
        marked_cells,recommended=markers_and_recommendations(cells,probabilities,certain,self.data.get('predictedTreasure',[]),candidates,self.data.get('allIdentified',False))
        marked_cells=sorted(set(marked_cells)|set(self.data.get('completedTreasure',[])))
        available=[v for i,v in enumerate(probabilities) if v is not None and i<len(cells) and cells[i]==0 and i not in marked_cells]
        maximum=max(available,default=0);minimum=min(available,default=0)
        for i,cell in enumerate(cells):
            value=probabilities[i] if i<len(probabilities) else None
            marked=i in marked_cells
            if not marked and (value is None or cell!=0):continue
            r,c=divmod(i,n);rect=QRectF(c*cw+2,r*ch+2,cw-4,ch-4)
            best=i in recommended
            ratio=(value-minimum)/(maximum-minimum) if not marked and maximum>minimum else 0
            color=QColor(255,212,66,145) if marked else QColor(*probability_fill(ratio,best))
            p.setPen(Qt.NoPen);p.setBrush(color);p.drawRoundedRect(rect,5,5)
            if marked:
                side=min(cw,ch)*.48
                self.chest.render(p,QRectF(rect.center().x()-side/2,rect.center().y()-side/2-(4 if cell==0 and i not in certain else 0),side,side))
                if cell==0 and i not in certain:
                    p.setPen(QColor('#000000'));font=QFont('Chiron GoRound TC');font.setPixelSize(max(10,min(14,round(cw*.21))));font.setBold(True);p.setFont(font)
                    p.drawText(rect.adjusted(2,2,-2,-2),Qt.AlignBottom|Qt.AlignHCenter,'推断')
                if best:
                    p.setPen(QColor('#000000'));font=QFont('Chiron GoRound TC');font.setPixelSize(max(10,min(14,round(cw*.21))));font.setBold(True);p.setFont(font)
                    p.drawText(rect.adjusted(2,2,-2,-2),Qt.AlignTop|Qt.AlignHCenter,'推荐')
                continue
            p.setPen(QColor('#000000'));font=QFont('Chiron GoRound TC');font.setPixelSize(max(9,min(17,round(cw*.25))));font.setBold(True);p.setFont(font)
            shown=self.display_probabilities[i] if i<len(self.display_probabilities) and self.display_probabilities[i] is not None else value
            p.drawText(rect,Qt.AlignCenter,f'{round(shown*100)}%')
            if best:
                font.setPixelSize(max(10,min(14,round(cw*.21))));font.setBold(True);p.setFont(font)
                p.drawText(rect.adjusted(3,2,-2,-2),Qt.AlignTop|Qt.AlignHCenter,'推荐')
