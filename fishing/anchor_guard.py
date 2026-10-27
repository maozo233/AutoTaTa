"""Preflight the fixed MAA 5.14.2 anchor; refuses known unsafe overlays."""
import ctypes as C
from ctypes import wintypes as W
import os

user32=C.WinDLL('user32',use_last_error=True)
user32.GetWindowRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
user32.GetWindowRect.restype=W.BOOL
user32.WindowFromPoint.argtypes=[W.POINT]
user32.WindowFromPoint.restype=W.HWND
user32.GetAncestor.argtypes=[W.HWND,W.UINT]
user32.GetAncestor.restype=W.HWND
user32.GetClassNameW.argtypes=[W.HWND,W.LPWSTR,C.c_int]
user32.GetClassNameW.restype=C.c_int
user32.GetWindowLongPtrW.argtypes=[W.HWND,C.c_int]
user32.GetWindowLongPtrW.restype=C.c_ssize_t
CALLBACK=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
user32.EnumWindows.argtypes=[CALLBACK,W.LPARAM]
user32.EnumWindows.restype=W.BOOL


def anchor_centers(bounds,target):
    left,top,width,height=bounds
    origins=((left+8,top+8),(left+width-12,top+8),
             (left+8,top+height-12),(left+width-12,top+height-12))
    for x,y in origins:
        if not (x<target[2] and x+4>target[0] and y<target[3] and y+4>target[1]):
            return (x+2,y+2)
    return (origins[0][0]+2,origins[0][1]+2)


def class_name(hwnd):
    name=C.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd,name,len(name))
    return name.value


def own_anchors():
    anchors=[]
    prefix=f'MaaAnchoredTouch_{os.getpid()}_'
    @CALLBACK
    def visit(hwnd,_):
        if class_name(hwnd).startswith(prefix):
            rect=W.RECT()
            if user32.GetWindowRect(hwnd,C.byref(rect)):
                anchors.append(((rect.left+rect.right)//2,(rect.top+rect.bottom)//2))
        return True
    user32.EnumWindows(visit,0)
    return anchors


def unsafe_overlay(name,root_name,topmost):
    # Our existing touch-anchor is the intended receiver, even though topmost.
    prefix=f'MaaAnchoredTouch_{os.getpid()}_'
    if name.startswith(prefix) or root_name.startswith(prefix):return False
    return 'myfinder' in (name+' '+root_name).lower() or topmost


def check_anchor(hwnd):
    points=own_anchors()
    if not points:
        rect=W.RECT()
        if not user32.GetWindowRect(hwnd,C.byref(rect)):
            raise RuntimeError('无法确认后台触摸锚点位置，已停止。')
        bounds=tuple(user32.GetSystemMetrics(index) for index in (76,77,78,79))
        points=[anchor_centers(bounds,(rect.left,rect.top,rect.right,rect.bottom))]
    for x,y in points:
        hit=user32.WindowFromPoint(W.POINT(x,y))
        if not hit:raise RuntimeError('无法确认后台触摸锚点接收窗口，已停止。')
        root=user32.GetAncestor(hit,2) or hit
        name,root_name=class_name(hit),class_name(root)
        topmost=bool(user32.GetWindowLongPtrW(root,-20)&8)
        if unsafe_overlay(name,root_name,topmost):
            raise RuntimeError(f'后台触摸锚点 ({x},{y}) 被 MyFinder 或置顶浮层占用，已在点击前停止，避免误点其他窗口。请移开或隐藏该浮层后重新开始。')
