"""Window targeting and WGC capture adapted from HoloDream AutoFish."""
import ctypes as C
from ctypes import wintypes as W
from pathlib import PureWindowsPath
import threading
import logging
import time
from .maa_input import MaaInput

user32 = C.WinDLL('user32', use_last_error=True)
kernel32 = C.WinDLL('kernel32', use_last_error=True)
dwmapi = C.WinDLL('dwmapi')

def api(dll, name, args, result):
    fn = getattr(dll, name)
    fn.argtypes, fn.restype = args, result
    return fn

api(user32, 'IsWindow', [W.HWND], W.BOOL)
api(user32, 'IsWindowVisible', [W.HWND], W.BOOL)
api(user32, 'IsIconic', [W.HWND], W.BOOL)
api(user32, 'GetClientRect', [W.HWND, C.POINTER(W.RECT)], W.BOOL)
api(user32, 'GetWindowRect', [W.HWND, C.POINTER(W.RECT)], W.BOOL)
api(user32, 'ClientToScreen', [W.HWND, C.POINTER(W.POINT)], W.BOOL)
api(user32, 'GetForegroundWindow', [], W.HWND)
api(user32, 'GetAncestor', [W.HWND, W.UINT], W.HWND)
api(user32, 'WindowFromPoint', [W.POINT], W.HWND)
api(user32, 'GetWindowThreadProcessId', [W.HWND, C.POINTER(W.DWORD)], W.DWORD)
api(user32, 'GetWindowTextLengthW', [W.HWND], C.c_int)
api(user32, 'GetWindowTextW', [W.HWND, W.LPWSTR, C.c_int], C.c_int)
api(user32, 'GetAsyncKeyState', [C.c_int], C.c_short)
api(user32, 'PostMessageW', [W.HWND, W.UINT, W.WPARAM, W.LPARAM], W.BOOL)
api(kernel32, 'OpenProcess', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE)
api(kernel32, 'CloseHandle', [W.HANDLE], W.BOOL)
api(kernel32, 'QueryFullProcessImageNameW', [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)], W.BOOL)
api(dwmapi, 'DwmGetWindowAttribute', [W.HWND, W.DWORD, C.c_void_p, W.DWORD], C.c_long)

def dpi_awareness():
    try:
        api(user32, 'SetProcessDpiAwarenessContext', [C.c_void_p], W.BOOL)(C.c_void_p(-4))
    except AttributeError:
        user32.SetProcessDPIAware()

def process_id(hwnd):
    pid = W.DWORD()
    user32.GetWindowThreadProcessId(hwnd, C.byref(pid))
    return pid.value

def process_path(pid):
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return ''
    try:
        size = W.DWORD(32768)
        text = C.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, text, C.byref(size)):
            return text.value
        return ''
    finally:
        kernel32.CloseHandle(handle)

def process_name(pid):
    return PureWindowsPath(process_path(pid)).name


def client_rect(hwnd):
    if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        raise RuntimeError('窗口已关闭或最小化，请恢复后重新开始。')
    rect, point = W.RECT(), W.POINT(0, 0)
    if not user32.GetClientRect(hwnd, C.byref(rect)) or not user32.ClientToScreen(hwnd, C.byref(point)):
        raise RuntimeError('无法读取窗口尺寸。')
    if rect.right < 250 or rect.bottom < 484:
        raise RuntimeError(f'当前窗口客户区为 {rect.right}×{rect.bottom}，尺寸过小。'
                           '需要至少 250×484；建议使用 315×599 或更大。'
                           '尺寸不含边框，包含模拟器顶部工具栏。放大后重新开始。')
    return point.x, point.y, rect.right, rect.bottom

def window_details():
    entries = []
    callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    @callback_type
    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            pid = process_id(hwnd)
            if process_name(pid).lower() == 'mumunxdevice.exe':
                text = C.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
                user32.GetWindowTextW(hwnd, text, len(text))
                try:
                    size = client_rect(hwnd)[2:]
                    entries.append(dict(hwnd=int(hwnd), pid=pid, title=text.value, size=size))
                except RuntimeError:
                    # Keep undersized windows selectable so Start can explain the size requirement.
                    rect = W.RECT()
                    if not user32.IsIconic(hwnd) and user32.GetClientRect(hwnd, C.byref(rect)):
                        entries.append(dict(hwnd=int(hwnd), pid=pid, title=text.value, size=(rect.right, rect.bottom)))
        return True
    api(user32, 'EnumWindows', [callback_type, W.LPARAM], W.BOOL)(visit, 0)
    return entries

def crop_client(frame, hwnd):
    x, y, width, height = client_rect(hwnd)
    fh, fw = frame.shape[:2]
    if (fw, fh) == (width, height):
        return frame[:, :, :3].copy(), (width, height)
    outer, extended = W.RECT(), W.RECT()
    bounds = []
    if dwmapi.DwmGetWindowAttribute(hwnd, 9, C.byref(extended), C.sizeof(extended)) == 0:
        bounds.append(extended)
    if user32.GetWindowRect(hwnd, C.byref(outer)):
        bounds.append(outer)
    for rect in bounds:
        if abs(rect.right-rect.left-fw) <= 2 and abs(rect.bottom-rect.top-fh) <= 2:
            left, top = x-rect.left, y-rect.top
            if left >= 0 and top >= 0 and left+width <= fw and top+height <= fh:
                return frame[top:top+height, left:left+width, :3].copy(), (width, height)
    raise RuntimeError('捕获坐标与窗口不匹配，请固定窗口大小后重试。')

class WindowCapture:
    def __init__(self, hwnd):
        from windows_capture import WindowsCapture
        self.hwnd = hwnd
        self.lock = threading.Lock()
        self.latest = None
        self.error = None
        self.sequence = 0
        self.control = None
        self.capture = WindowsCapture(window_hwnd=hwnd, cursor_capture=False, draw_border=True, minimum_update_interval=16)
        @self.capture.event
        def on_frame_arrived(frame, capture_control):
            try:
                array, size = crop_client(frame.frame_buffer, hwnd)
                with self.lock:
                    self.sequence += 1
                    self.latest = array, time.monotonic(), self.sequence, size
            except Exception as exc:
                self.error = str(exc)
                capture_control.stop()
        @self.capture.event
        def on_closed():
            self.error = '捕获已结束，请重新开始。'

    def start(self):
        self.control = self.capture.start_free_threaded()

    def read(self):
        if self.error:
            raise RuntimeError(self.error)
        with self.lock:
            return self.latest

    def close(self):
        if self.control:
            self.control.stop()
            self.control.wait()
            self.control = None

class FocusLost(RuntimeError):
    pass

class MOUSEINPUT(C.Structure):
    _fields_ = [('dx', W.LONG), ('dy', W.LONG), ('mouseData', W.DWORD),
                ('dwFlags', W.DWORD), ('time', W.DWORD), ('dwExtraInfo', C.c_size_t)]

class KEYBDINPUT(C.Structure):
    _fields_ = [('wVk', W.WORD), ('wScan', W.WORD), ('dwFlags', W.DWORD),
                ('time', W.DWORD), ('dwExtraInfo', C.c_size_t)]

class INPUTUNION(C.Union):
    _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT)]

class INPUT(C.Structure):
    _anonymous_ = ('data',)
    _fields_ = [('type', W.DWORD), ('data', INPUTUNION)]

api(user32, 'SendInput', [W.UINT, C.POINTER(INPUT), C.c_int], W.UINT)

def start_screen_clip():
    """Open Windows' standard region-to-clipboard shortcut on user request."""
    keys=(0x5B,0x10,0x53)  # Windows, Shift, S.
    def event(key,released=False):
        flags=(1 if key==0x5B else 0)|(2 if released else 0)
        return INPUT(type=1,ki=KEYBDINPUT(key,0,flags,0,0))
    events=(INPUT*6)(*[event(k) for k in keys],*[event(k,True) for k in reversed(keys)])
    if user32.SendInput(len(events),events,C.sizeof(INPUT))!=len(events):
        # A partial send must never leave a modifier key pressed.
        release=(INPUT*3)(*[event(k,True) for k in reversed(keys)])
        user32.SendInput(len(release),release,C.sizeof(INPUT))
        raise OSError('Windows screenshot shortcut could not be sent')

class Mouse:
    def __init__(self, hwnd, mode, cancel):
        self.hwnd, self.pid, self.mode, self.cancel = hwnd, process_id(hwnd), mode, cancel
        self.size = client_rect(hwnd)[2:]
        self.backend = MaaInput(hwnd, 'foreground' if mode == 'foreground' else 'background')
        self.backend.prepare(self.size)

    def validate(self, point):
        if self.cancel.is_set():
            return False
        if process_id(self.hwnd) != self.pid or process_name(self.pid).lower() != 'mumunxdevice.exe':
            raise RuntimeError('目标进程已改变，已停止。')
        x, y, w, h = client_rect(self.hwnd)
        if (w, h) != self.size:
            raise RuntimeError('窗口尺寸已改变，请重新开始。')
        if self.mode == 'foreground':
            if user32.GetForegroundWindow() != self.hwnd:
                raise FocusLost('游戏不在前台，已暂停；切回游戏后继续。')
            hit = user32.WindowFromPoint(W.POINT(x+point[0], y+point[1]))
            if user32.GetAncestor(hit, 2) != self.hwnd:
                raise FocusLost('操作区域被遮挡，已暂停。')
        return True

    def click(self, point):
        point = tuple(map(round, point))
        if not self.validate(point):
            return
        try:
            self.backend.down(*point)
        except Exception:
            # Down may have failed before creating a contact. Clear any partial
            # contact without sending an invalid up or masking the original error.
            try:
                self.backend.deactivate()
            except Exception:
                logging.getLogger('fishing').exception('Cleanup after touch-down failure failed')
            raise
        try:
            self.cancel.wait(.045 if self.mode == 'foreground' else .08)
        finally:
            if self.mode == 'foreground' and user32.GetForegroundWindow() != self.hwnd:
                # Do not let Seize reactivate the game after the user switches away.
                self.emergency_release(point)
                self.backend.deactivate()
            else:
                try:
                    self.backend.up()
                except Exception:
                    self.emergency_release(point)
                    raise

    def emergency_release(self, point):
        if self.mode == 'foreground':
            event = INPUT(type=0, mi=MOUSEINPUT(0, 0, 0, 0x0004, 0, 0))
            if user32.SendInput(1, C.byref(event), C.sizeof(INPUT)) != 1:
                raise RuntimeError('紧急松键失败，请检查权限。')
        else:
            # Synthetic touch contacts must be released through MAA, not WM_LBUTTONUP.
            self.backend.deactivate()

    def close(self):
        self.backend.deactivate()


def fullscreen_covering(hwnd):
    """Check actual screen occlusion, including topmost covers without focus."""
    target=W.RECT()
    if not user32.GetWindowRect(hwnd,C.byref(target)):return False
    root=user32.GetAncestor(hwnd,2)
    hit=user32.WindowFromPoint(W.POINT((target.left+target.right)//2,(target.top+target.bottom)//2))
    candidates=[user32.GetForegroundWindow(),user32.GetAncestor(hit,2)]
    class MonitorInfo(C.Structure):
        _fields_=[('cbSize',W.DWORD),('rcMonitor',W.RECT),('rcWork',W.RECT),('dwFlags',W.DWORD)]
    for candidate in candidates:
        if not candidate or user32.GetAncestor(candidate,2)==root:continue
        a=W.RECT()
        if not user32.IsWindowVisible(candidate) or not user32.GetWindowRect(candidate,C.byref(a)):continue
        monitor=api(user32,'MonitorFromWindow',[W.HWND,W.DWORD],W.HANDLE)(candidate,2)
        info=MonitorInfo();info.cbSize=C.sizeof(info)
        if not api(user32,'GetMonitorInfoW',[W.HANDLE,C.c_void_p],W.BOOL)(monitor,C.byref(info)):continue
        m=info.rcMonitor
        zoomed=api(user32,'IsZoomed',[W.HWND],W.BOOL)(candidate)
        large=(a.right-a.left>=(m.right-m.left)*.95 and a.bottom-a.top>=(m.bottom-m.top)*.90)
        overlap=max(0,min(a.right,target.right)-max(a.left,target.left))*max(0,min(a.bottom,target.bottom)-max(a.top,target.top))
        area=max(1,(target.right-target.left)*(target.bottom-target.top))
        if (zoomed or large) and overlap/area>=.75:return True
    return False
