"""Native Windows decoration for our custom, opaque Qt Quick windows.

Keep the client area and custom title bar intact. DWM supplies the outside
shadow, border and (on Windows 11) corners; no extra QML margins are needed.
"""
import ctypes
import logging
import sys
from ctypes import wintypes

from PySide6.QtCore import QObject, QEvent, QTimer, QAbstractNativeEventFilter
from PySide6.QtGui import QGuiApplication


class _Margins(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int) for name in ('left', 'right', 'top', 'bottom')]


class _Messages(QAbstractNativeEventFilter):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def nativeEventFilter(self, event_type, pointer):
        if not self.owner.hwnd:
            return False, 0
        msg = wintypes.MSG.from_address(int(pointer))
        if msg.hWnd != self.owner.hwnd:
            return False, 0
        if msg.message == 0x0083:  # WM_NCCALCSIZE: retain the full client area.
            return True, 0
        if msg.message == 0x0084:  # WM_NCHITTEST: use the existing aspect-ratio grip.
            return True, 1        # HTCLIENT; startSystemMove still handles our header.
        if msg.message in (0x0006, 0x007D, 0x031E):  # activation / styles / composition
            if msg.message == 0x031E:
                self.owner.decorated_hwnd = 0
            self.owner.schedule()
        return False, 0


class WindowFrame(QObject):
    """One controller per root window, also used by every standalone entrypoint."""
    def __init__(self, window, popup=False):
        super().__init__(window)
        self.window = window
        self.popup = popup
        self.hwnd = 0
        self.decorated_hwnd = 0
        self.closed = False
        self.errors = []
        self.application = QGuiApplication.instance()
        self.enabled = sys.platform == 'win32' and self.application.platformName() == 'windows'
        if not self.enabled:
            return
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.dwm = ctypes.WinDLL('dwmapi')
        for name, args, result in (
            ('GetWindowLongPtrW', [wintypes.HWND, ctypes.c_int], ctypes.c_ssize_t),
            ('SetWindowLongPtrW', [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t], ctypes.c_ssize_t),
            ('SetWindowPos', [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.BOOL),
        ):
            function = getattr(self.user, name)
            function.argtypes, function.restype = args, result
        self.dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        self.dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        self.dwm.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, ctypes.c_void_p]
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.apply)
        self.messages = _Messages(self)
        self.application.installNativeEventFilter(self.messages)
        window.installEventFilter(self)
        window.visibleChanged.connect(self.schedule)
        window.opacityChanged.connect(self.schedule)
        self.application.aboutToQuit.connect(self.close)
        self.apply()

    def schedule(self, *_):
        if self.enabled and not self.closed:
            self.timer.start(0)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Show, QEvent.Type.WinIdChange,
                            QEvent.Type.PlatformSurface, QEvent.Type.WindowStateChange):
            self.schedule()
        return False

    def apply(self):
        if not self.enabled or self.closed:
            return
        try:
            self.hwnd = int(self.window.winId())
            style = self.user.GetWindowLongPtrW(self.hwnd, -16)
            # A standard native frame is required for DWM decoration. Suppress
            # its nonclient area above, rather than adding a system title bar.
            framed = style | 0x00C00000 | 0x00040000
            if not self.popup:framed &= ~0x80000000
            if framed == style and self.decorated_hwnd == self.hwnd:
                return
            if framed != style:
                ctypes.set_last_error(0)
                self.user.SetWindowLongPtrW(self.hwnd, -16, framed)
                if ctypes.get_last_error():
                    raise ctypes.WinError(ctypes.get_last_error())
            policy = ctypes.c_int(2)  # DWMNCRP_ENABLED
            self.dwm.DwmSetWindowAttribute(self.hwnd, 2, ctypes.byref(policy), 4)
            corners = ctypes.c_int(2)  # DWMWCP_ROUND; unsupported on Windows 10.
            self.dwm.DwmSetWindowAttribute(self.hwnd, 33, ctypes.byref(corners), 4)
            self.dwm.DwmExtendFrameIntoClientArea(self.hwnd, ctypes.byref(_Margins(1, 1, 1, 1)))
            if framed != style:
                # Refresh without moving, resizing, reordering or activating.
                if not self.user.SetWindowPos(self.hwnd, None, 0, 0, 0, 0, 0x0037):
                    raise ctypes.WinError(ctypes.get_last_error())
            self.decorated_hwnd = self.hwnd
        except OSError as exc:
            message = str(exc)
            if message not in self.errors:
                self.errors.append(message)
                logging.warning('Native window frame: %s', message)

    def snapshot(self):
        """Native checks supplement, but do not replace, compositor visual QA."""
        result = {'enabled': self.enabled, 'errors': list(self.errors)}
        if self.enabled and self.hwnd:
            rendered = wintypes.BOOL()
            self.dwm.DwmGetWindowAttribute(self.hwnd, 1, ctypes.byref(rendered), ctypes.sizeof(rendered))
            style = self.user.GetWindowLongPtrW(self.hwnd, -16)
            result.update(frameStyles=(style & 0x00C40000) == 0x00C40000,
                          nativeRendering=bool(rendered.value),
                          opaque=self.window.property('color').alpha() == 255,
                          layered=bool(self.user.GetWindowLongPtrW(self.hwnd, -20) & 0x80000))
        return result

    def close(self):
        if self.enabled and not self.closed:
            self.closed = True
            self.timer.stop()
            self.application.removeNativeEventFilter(self.messages)
            self.window.removeEventFilter(self)
