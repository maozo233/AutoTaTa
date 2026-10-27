"""Unfinished cells on the target window; click-through and monitor-aware."""
import ctypes as C
from ctypes import wintypes as W
import numpy as np
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QGuiApplication,QImage,QPainter,QColor,QFont
from treasure.overlay import Overlay as TrackingOverlay
from .vision import Vision


class Overlay(TrackingOverlay):
    def __init__(self):
        super().__init__();self.vision=Vision();self.last_geometry=None
    def publish(self,data):
        self.data=dict(data);self.update()
    def bind(self,hwnd):
        super().bind(hwnd);self.last_geometry=None
    def track(self):
        if not self.active or not self.target or not self.data.get('issues'):
            self.hide();return
        from fishing.windows import user32,client_rect,api
        hwnd=self.target
        if (not user32.IsWindow(hwnd) or user32.IsIconic(hwnd) or
            user32.GetAncestor(user32.GetForegroundWindow(),2)!=user32.GetAncestor(hwnd,2)):
            self.hide();return
        try:
            x,y,w,h=client_rect(hwnd)
            class Info(C.Structure):
                _fields_=[('cbSize',W.DWORD),('monitor',W.RECT),('work',W.RECT),('flags',W.DWORD),('device',W.WCHAR*32)]
            info=Info();info.cbSize=C.sizeof(info)
            monitor=api(user32,'MonitorFromWindow',[W.HWND,W.DWORD],W.HANDLE)(hwnd,2)
            if not api(user32,'GetMonitorInfoW',[W.HANDLE,C.c_void_p],W.BOOL)(monitor,C.byref(info)):self.hide();return
            screen=next((s for s in QGuiApplication.screens() if s.name()==info.device),QGuiApplication.primaryScreen())
            dpr=screen.devicePixelRatio();origin=screen.geometry().topLeft()
            key=(w,h,dpr,self.data.get('grid',{}).get('columns'))
            if key!=self.last_geometry:
                self.hide()
                image=screen.grabWindow(0).toImage().convertToFormat(QImage.Format_RGB888).copy(x-info.monitor.left,y-info.monitor.top,w,h)
                if image.width()!=w or image.height()!=h:return
                pixels=np.frombuffer(image.bits(),np.uint8).reshape(h,image.bytesPerLine())[:,:w*3].reshape(h,w,3)[:,:,::-1].copy()
                found=self.vision.observe(pixels)
                if found.state!='ready' or found.grid.columns!=self.data['grid']['columns']:return
                self.mapping=found.grid.rect;self.last_geometry=key
            bx,by,bw,bh=self.mapping
            self.setGeometry(round(origin.x()+(x+bx-info.monitor.left)/dpr),round(origin.y()+(y+by-info.monitor.top)/dpr),round(bw/dpr),round(bh/dpr))
            self.show();self.update()
        except (RuntimeError,ValueError):self.hide()
    def paintEvent(self,event):
        if not self.data.get('grid'):return
        grid=self.data['grid'];cols,rows=grid['columns'],grid['rows'];cw,ch=self.width()/cols,self.height()/rows
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        font=QFont('Chiron GoRound TC');font.setPixelSize(max(10,min(13,round(cw*.18))));font.setBold(True);painter.setFont(font)
        for issue in self.data.get('issues',[]):
            row,col=divmod(issue['index'],cols)
            rect=QRectF(col*cw+2,row*ch+2,cw-4,ch-4)
            painter.setPen(QColor('#e66c57'));painter.setBrush(QColor(255,170,160,115));painter.drawRoundedRect(rect,6,6)
            painter.setPen(QColor('#101d42'));painter.drawText(rect.adjusted(2,2,-2,-2),Qt.AlignCenter|Qt.TextWordWrap,issue['reason'])
