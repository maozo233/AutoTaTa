"""Passive cursor diagnostics; never moves or blocks the user's mouse."""
import ctypes as C
from ctypes import wintypes as W
import logging
import threading

user32=C.WinDLL('user32',use_last_error=True)
user32.GetCursorPos.argtypes=[C.POINTER(W.POINT)]
user32.GetCursorPos.restype=W.BOOL
user32.WindowFromPoint.argtypes=[W.POINT]
user32.WindowFromPoint.restype=W.HWND
user32.GetClassNameW.argtypes=[W.HWND,W.LPWSTR,C.c_int]
user32.GetClassNameW.restype=C.c_int


def is_corner_jump(previous,current,bounds):
    if previous is None or abs(current[0]-previous[0])+abs(current[1]-previous[1])<300:
        return False
    left,top,width,height=bounds
    return any(abs(current[0]-x)<=32 and abs(current[1]-y)<=32
               for x in (left,left+width-1) for y in (top,top+height-1))


class CursorTrace:
    def __init__(self):
        self.phase='idle'
        self.stop_event=threading.Event()
        self.thread=None

    def start(self):
        if self.thread is not None:return
        self.thread=threading.Thread(target=self.monitor,daemon=True,name='background-cursor-trace')
        self.thread.start()

    def monitor(self):
        previous=None
        log=logging.getLogger('fishing')
        while not self.stop_event.wait(.01):
            point=W.POINT()
            if not user32.GetCursorPos(C.byref(point)):continue
            current=(point.x,point.y)
            bounds=tuple(user32.GetSystemMetrics(index) for index in (76,77,78,79))
            if self.phase!='idle' and is_corner_jump(previous,current,bounds):
                name=C.create_unicode_buffer(256)
                user32.GetClassNameW(user32.WindowFromPoint(point),name,len(name))
                log.warning('cursor corner jump phase=%s from=%s to=%s hit_class=%s; passive observation only',self.phase,previous,current,name.value)
            previous=current

    def close(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=.5)
