"""MaaFramework Win32 input; vision remains on the existing WGC capture loop."""
import threading
import time
import sys
import logging
import os
from .paths import settings_path
from .log_policy import log_cursor, cursor_offset, native_log_lock, start_maintenance

_init_lock = threading.Lock()
_initialized = False


def maa_log_path():
    folder = "maa" if getattr(sys, "frozen", False) else "build/maa"
    return settings_path().parent / folder / "debug/maafw.log"


def log_offset():
    return log_cursor(maa_log_path())


def new_input_failure(offset):
    """Use only errors from this operation and this process, never old sessions."""
    try:
        offset=cursor_offset(maa_log_path(),offset)
        with maa_log_path().open('rb') as stream:
            stream.seek(0, 2)
            end = stream.tell()
            if end < offset:
                return ''
            stream.seek(max(offset, end-8192))
            text = stream.read().decode('utf-8', errors='replace')
    except OSError:
        return ''
    errors = '\n'.join(line for line in text.splitlines()
                       if '[ERR]' in line and f'[Px{os.getpid()}]' in line)
    if 'still occluded after being raised' in errors:
        return '后台触摸位置仍被其他窗口遮挡，MAA抬高游戏后仍无法点击。请移开遮挡窗口或置顶浮层，再重新开始；也可切换前台模式。'
    if 'the target point is outside the desktop' in errors:
        return '后台触摸位置超出桌面。请把游戏窗口完整移入屏幕后重新开始。'
    return ''


def initialize():
    global _initialized
    with _init_lock:
        if not _initialized:
            from maa.toolkit import Toolkit
            start_maintenance()
            log_path = settings_path().parent / ("maa" if getattr(sys, "frozen", False) else "build/maa")
            if not Toolkit.init_option(log_path):
                raise RuntimeError("MaaFramework 初始化失败。")
            _initialized = True


def wait_job(job, timeout=1.5):
    deadline = time.monotonic() + timeout
    while not job.done:
        if time.monotonic() >= deadline:
            raise RuntimeError("MaaFramework 操作超时，已停止并尝试松键。")
        time.sleep(0.005)
    if not job.succeeded:
        raise RuntimeError("MaaFramework 操作失败，请检查窗口及权限。")


def create_controller(hwnd, mode):
    initialize()
    from maa.controller import Win32Controller
    from maa.define import MaaWin32InputMethodEnum as Input, MaaWin32ScreencapMethodEnum as Capture
    methods = {"foreground": Input.Seize, "background": Input.AnchoredTouch,
               "background_message": Input.PostMessage,
               "background_send": Input.SendMessage}
    method = methods[mode]
    return Win32Controller(hwnd, screencap_method=Capture.FramePool | Capture.PrintWindow,
                           mouse_method=method,
                           keyboard_method=Input.PostMessage if mode == "background" else method)


class MaaInput:
    def __init__(self, hwnd, mode):
        self.hwnd, self.mode = hwnd, mode
        self.log = logging.getLogger("autofish.session")
        self.controller = create_controller(hwnd, mode)
        self.ready = False
        self.cursor_trace = None

    def prepare(self, size):
        if self.ready:
            return
        if not self.controller.set_screenshot_use_raw_size(True):
            raise RuntimeError("MaaFramework 原始坐标设置失败。")
        # Win32's initial capture benchmark alone takes about two seconds.
        try:
            wait_job(self.controller.post_connection(), timeout=8.0)
        except RuntimeError as exc:
            raise RuntimeError(f"连接游戏窗口失败（尚未发送点击）：{exc}") from exc
        # Initialize MAA's coordinate mapping before any input is submitted.
        try:
            wait_job(self.controller.post_screencap(), timeout=4.0)
        except RuntimeError as exc:
            raise RuntimeError(f"输入坐标截图失败（尚未发送点击）：{exc}") from exc
        if tuple(self.controller.resolution) != tuple(size):
            raise RuntimeError("MaaFramework 捕获尺寸与游戏内容不一致，已停止。")
        self.log.info("input mapping ready hwnd=%s mode=%s resolution=%s", self.hwnd, self.mode, size)
        self.ready = True
        if self.mode == "background":
            from .cursor_trace import CursorTrace
            self.cursor_trace = CursorTrace()
            self.cursor_trace.start()

    def down(self, x, y):
        with native_log_lock:
            if self.mode == "background":
                from .anchor_guard import check_anchor
                check_anchor(self.hwnd)
            trace = getattr(self, "cursor_trace", None)
            if trace: trace.phase = "touch-down"
            offset = log_offset()
            job = self.controller.post_touch_down(x, y, contact=0)
            self.log.info("input down submitted hwnd=%s mode=%s client=(%s,%s) job=%s", self.hwnd, self.mode, x, y, job.job_id)
            try:
                wait_job(job)
            except RuntimeError as exc:
                detail = new_input_failure(offset)
                if trace: trace.phase = "down-failed"
                raise RuntimeError(detail or f'{exc}（触摸按下，任务 {job.job_id}）') from exc
            self.log.info("input down completed job=%s", job.job_id)
            if trace: trace.phase = "holding-touch"

    def up(self):
        trace = getattr(self, "cursor_trace", None)
        if trace: trace.phase = "touch-up"
        job = self.controller.post_touch_up(contact=0)
        wait_job(job)
        self.log.info("input up completed hwnd=%s mode=%s job=%s", self.hwnd, self.mode, job.job_id)
        if trace: trace.phase = "idle"

    def deactivate(self):
        trace = getattr(self, "cursor_trace", None)
        if trace: trace.phase = "inactive"
        try:
            wait_job(self.controller.post_inactive(), timeout=3.0)
        finally:
            if trace: trace.close()
