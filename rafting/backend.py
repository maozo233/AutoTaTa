import json
import queue
import shutil
import threading
import time
import math
import logging
from dataclasses import asdict
from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, Qt
from autotata.paths import ROOT
from .engine import Settings, REWARDS, MULTIPLIERS

MODES = ('mumu_sdk', 'foreground', 'maatouch')


class RaftingBackend(QObject):
    changed = Signal()
    devicesReady = Signal(int, object, str)

    def __init__(self, discover=True):
        super().__init__()
        self.worker = None
        self.cancel = threading.Event()
        self.events = queue.Queue()
        self.updates = queue.Queue()
        self.entries = []
        self.generation = 0
        self.closing = False
        self.hotkeys = False
        self.manual_stop = False
        self.readings_target = None
        self.shutdown_deadline = None
        self.window = None
        self.window_was_topmost = None
        self.settings = Settings()
        try:
            saved = json.loads((ROOT/'rafting-settings.json').read_text(encoding='utf-8'))
            self.settings = Settings(**{k: v for k, v in saved.items() if k in asdict(self.settings)})
        except (OSError, ValueError, TypeError):
            pass
        if self.settings.mode not in MODES:
            self.settings.mode = MODES[0]
        if self.settings.desired_multiplier not in MULTIPLIERS:
            self.settings.desired_multiplier = 50
        if not isinstance(self.settings.priority, list) or any(not isinstance(k,str) for k in self.settings.priority) or sorted(self.settings.priority) != sorted(k for k, _ in REWARDS):
            self.settings.priority = [k for k, _ in REWARDS]
        for key in ('crop_top', 'crop_bottom', 'boat_budget'):
            value = getattr(self.settings, key)
            if not isinstance(value, int) or value < 0:
                setattr(self.settings, key, 0)
        self.settings.shutdown_on_stop = False
        if not isinstance(self.settings.shutdown_force, bool):self.settings.shutdown_force = False
        self._state = {**asdict(self.settings), 'modeIndex': MODES.index(self.settings.mode),
                       'devices': [], 'deviceIndex': -1, 'deviceText': '', 'refreshing': False,
                       'running': False, 'canClose': False, 'rounds': 0, 'used': 0, 'stock': None,
                       'currentMultiplier': None, 'maximum': False, 'phase': 'unknown',
                       'normalStop': False, 'shutdownPending': False, 'shutdownStatus': '',
                       'status': '选择设备，在漂流大赛任意活动界面开始'}
        self.devicesReady.connect(self.finishDevices)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        if discover:
            QTimer.singleShot(0, self.refresh)

    @Property('QVariantMap', notify=changed)
    def state(self):
        values = self._state.copy()
        values['multipliers'] = list(MULTIPLIERS)
        values['rewards'] = [{'key': k, 'name': dict(REWARDS)[k]} for k in self.settings.priority]
        return values

    def update(self, **values):
        # Last successful reads are presentation only. The engine continues
        # to receive fresh observations, never these retained display values.
        values=self.displayValues(values)
        if any(self._state.get(k) != v for k, v in values.items()):
            self._state.update(values)
            self.changed.emit()

    @staticmethod
    def displayValues(values):
        values=dict(values)
        if values.get('stock') is None:values.pop('stock',None)
        if 'currentMultiplier' in values and values['currentMultiplier'] is None:
            values.pop('currentMultiplier')
            values.pop('maximum',None)
        return values

    def clearReadings(self):
        self._state.update(stock=None,currentMultiplier=None,maximum=False)
        self.changed.emit()

    def persist(self):
        try:
            values = asdict(self.settings)
            values['shutdown_on_stop'] = False
            (ROOT/'rafting-settings.json').write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError:
            self.update(status='设置保存失败，请检查目录权限')

    @Slot(str, 'QVariant')
    def setValue(self, key, value):
        if key in ('shutdown_on_stop', 'shutdown_force'):
            setattr(self.settings,key,bool(value))
            self.update(**{key:bool(value)})
            if key == 'shutdown_on_stop' and not value:self.cancelShutdown()
            self.persist()
            return
        if key not in ('desired_multiplier', 'crop_top', 'crop_bottom', 'boat_budget'):
            return
        try:
            value = int(value)
        except (ValueError, TypeError):
            return
        if value < 0 or key == 'desired_multiplier' and value not in MULTIPLIERS:
            return
        if self._state['running'] and key.startswith('crop_'):
            self.update(status='请先停止，再修改画面边距')
            return
        setattr(self.settings, key, value)
        self.update(**{key: value})
        if self._state['running']:
            self.updates.put({key: value})
        self.persist()

    @Slot()
    def restoreRecommended(self):
        order = [k for k, _ in REWARDS]
        self.settings.priority = order
        self.update(priority=order)
        self.changed.emit()
        if self._state['running']:self.updates.put({'priority': order})
        self.persist()

    @Slot(int, int)
    def moveReward(self, source, target):
        if source not in range(6) or target not in range(6) or source == target:
            return
        order = list(self.settings.priority)
        order.insert(target, order.pop(source))
        self.settings.priority = order
        self.update(priority=order)
        self.changed.emit()
        if self._state['running']:
            self.updates.put({'priority': order})
        self.persist()

    @Slot(int)
    def setMode(self, index):
        if index not in range(3) or self._state['running']:
            return
        if index!=self._state['modeIndex']:self.clearReadings()
        self.settings.mode = MODES[index]
        self.update(modeIndex=index, mode=MODES[index], deviceIndex=-1)
        self.persist()
        self.refresh()

    @Slot(int)
    def selectDevice(self, index):
        if not self._state['running'] and index in range(len(self.entries)):
            if index!=self._state['deviceIndex']:self.clearReadings()
            self.update(deviceIndex=index, deviceText=self._state['devices'][index])

    @Slot(str)
    def setAddress(self, address):
        if not self._state['running']:
            if address.strip()!=self._state['deviceText']:self.clearReadings()
            self.update(deviceText=address.strip(), deviceIndex=-1)

    @Slot()
    def refresh(self):
        if self._state['running'] or self.closing:
            return
        self.generation += 1
        generation, mode = self.generation, self.settings.mode
        self.update(refreshing=True)
        def discover():
            try:
                if mode == 'maatouch':
                    from fishing.generic_adb import discover_adb_entries
                    entries = discover_adb_entries()
                else:
                    from fishing.windows import window_details
                    entries = window_details()
                self.devicesReady.emit(generation, entries, '')
            except Exception as exc:
                self.devicesReady.emit(generation, [], str(exc))
        threading.Thread(target=discover, daemon=True).start()

    @Slot(int, object, str)
    def finishDevices(self, generation, entries, error):
        if generation != self.generation or self.closing:
            return
        self.entries = entries
        target=(self.settings.mode,entries[0].get('hwnd'),entries[0].get('adb_address')) if entries else None
        if self.readings_target is not None and target!=self.readings_target:self.clearReadings()
        titles = [e['title'] if self.settings.mode=='maatouch' else
                  f"{e['title']} · {e['size'][0]}×{e['size'][1]} · PID {e['pid']}" for e in entries]
        self.update(devices=titles, deviceIndex=0 if titles else -1, deviceText=titles[0] if titles else '', refreshing=False)
        if error:
            self.update(status=f'设备发现失败：{error}')

    @Slot()
    def start(self):
        if self._state['running'] or self.closing or self._state['refreshing'] or self._state['shutdownPending']:
            return
        index = self._state['deviceIndex']
        if index not in range(len(self.entries)):
            if self.settings.mode == 'maatouch' and self._state['deviceText']:
                adb = self.entries[0]['adb_path'] if self.entries else shutil.which('adb')
                if adb:
                    entry = {'hwnd': None, 'adb_path': str(adb), 'adb_address': self._state['deviceText']}
                else:
                    self.update(status='未找到 ADB，请安装模拟器并刷新设备')
                    return
            else:
                self.update(status='请选择设备后开始')
                return
        else:
            entry = self.entries[index]
        settings = Settings(**asdict(self.settings))
        target=(settings.mode,entry.get('hwnd'),entry.get('adb_address'))
        if self.readings_target is not None and target!=self.readings_target:self.clearReadings()
        self.readings_target=target
        if settings.mode == 'maatouch':
            settings.adb_path = str(entry['adb_path'])
            settings.adb_address = entry['adb_address']
        from .runner import run
        self.cancel = threading.Event()
        self.manual_stop = False
        self.events = queue.Queue()
        self.updates = queue.Queue()
        self.update(running=True, normalStop=False, shutdownStatus='', rounds=0, used=0, status='正在连接设备…')
        self.worker = threading.Thread(target=run, args=(entry.get('hwnd'), settings, self.cancel, self.events.put, self.updates), daemon=True)
        self.worker.start()

    @Slot()
    def stop(self):
        self.manual_stop = True
        self.cancelShutdown()
        self.cancel.set()
        if self._state['running']:self.update(status='正在停止并释放操作…')

    @Slot()
    def close(self):
        self.closing = True
        self.stop()
        self.poll()

    def poll(self):
        if self.hotkeys:
            from fishing.windows import user32
            from fishing.hotkeys import START_KEY, STOP_KEY
            if user32.GetAsyncKeyState(STOP_KEY) & 1:
                self.stop()
            if user32.GetAsyncKeyState(START_KEY) & 1:
                self.start()
        changes = {}
        while True:
            try:
                changes.update(self.displayValues(self.events.get_nowait()))
            except queue.Empty:
                break
        if changes:
            self.update(**changes)
        if not self.worker or not self.worker.is_alive():
            finished = self._state['running']
            if self._state['running'] and self.manual_stop and not self._state['status'].startswith('连接释放失败'):
                self.update(status='已停止')
            self.update(running=False, canClose=self.closing)
            if finished and self._state['normalStop'] and self._state['shutdown_on_stop'] and not self.manual_stop and not self.closing:
                self.shutdown_deadline = time.monotonic()+15
                self.update(normalStop=False, shutdownPending=True, shutdownStatus='15 秒后关机')
                if self.window is not None:
                    self.window_was_topmost = bool(self.window.flags() & Qt.WindowStaysOnTopHint)
                    self.window.setFlag(Qt.WindowStaysOnTopHint,True)
                    self.window.showNormal();self.window.raise_();self.window.requestActivate()
        self.tickShutdown()

    @Slot()
    def cancelShutdown(self):
        if self._state['shutdownPending']:
            self.shutdown_deadline = None
            self.update(shutdownPending=False, normalStop=False, shutdownStatus='已取消本次关机')
            self.restoreWindow()

    def restoreWindow(self):
        if self.window is not None and self.window_was_topmost is not None:
            self.window.setFlag(Qt.WindowStaysOnTopHint,self.window_was_topmost)
        self.window_was_topmost = None

    def tickShutdown(self):
        if not self._state['shutdownPending']:return
        if self.manual_stop or self.closing or not self._state['shutdown_on_stop']:
            self.cancelShutdown();return
        remaining = max(0,math.ceil(self.shutdown_deadline-time.monotonic()))
        if remaining:
            self.update(shutdownStatus=f'{remaining} 秒后关机');return
        self.shutdown_deadline = None
        self.update(shutdownPending=False, shutdownStatus='正在请求关机…')
        self.restoreWindow()
        try:
            from fishing.shutdown import request_shutdown
            request_shutdown(bool(self._state['shutdown_force']))
            self.update(shutdownStatus='已发送关机请求')
        except Exception as exc:
            logging.exception('Rafting shutdown request failed')
            self.update(shutdownStatus='关机请求失败，请手动关机。',status=f'关机请求失败：{exc}')
