"""Qt Quick GPU frontend; engine/input remain on the existing worker thread."""
import json
import logging
import queue
import re
import shutil
import sys
import threading
import time
import math
from dataclasses import asdict
from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, QUrl, Qt
from PySide6.QtGui import QGuiApplication, QFontDatabase, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from .paths import ROOT, ASSETS
from .engine import Settings
from .hotkeys import START_KEY, STOP_KEY
from .windows import window_details, user32, client_rect
from .runner import run

UI_ZOOMS=(.5,.75,1.,1.25,1.5,1.75,2.)
MODE_LABELS={'mumu_sdk':'后台 MuMuSDK','foreground':'前台 Maa','maatouch':'通用兼容后台 ADB + MaaTouch'}

class Backend(QObject):
    changed=Signal()
    devicesReady=Signal(int, object, str)
    warning=Signal(str, str)
    pulse=Signal(str)
    def __init__(self, discover=True, hotkeys=True):
        super().__init__()
        self.events=queue.Queue();self.session_updates=queue.Queue()
        self.worker=None;self.cancel=threading.Event();self.session_settings=None
        self.pending_change=None;self.resume_counts=None;self.resume_hwnd=None;self.manual_stop=False
        self.entries=[];self.window=None;self.generation=0;self.hotkeys=hotkeys
        settings=Settings(auto_bait=True,full_bait_protection=True)
        try:
            values=json.loads((ROOT/'settings.json').read_text(encoding='utf-8'))
            values.setdefault('full_bait_protection',True)
            settings=Settings(**{k:v for k,v in values.items() if k in asdict(settings)})
        except (OSError,ValueError,TypeError):pass
        settings.shutdown_on_stop=False  # Each launch requires an explicit opt-in.
        if settings.mode=='background':settings.mode='maatouch'
        if settings.mode not in MODE_LABELS:settings.mode='mumu_sdk'
        if not isinstance(settings.ui_scale,(float,int)) or not .5<=settings.ui_scale<=2.:settings.ui_scale=1.
        # Retired UI option must not silently disable the new maintenance policy.
        settings.stop_when_buffs_end=False
        self.shutdown_deadline=None
        self.shutdown_window_was_topmost=None
        self.settings=settings
        self._state={**asdict(settings),'modeIndex':list(MODE_LABELS).index(settings.mode),
                     'devices':[],'deviceIndex':-1,'deviceText':'请选择设备','refreshing':False,
                     'baitDeadline':None,'baitPhase':None,'baitAtLimit':False,'baitUsed':0,
                     'rodLevel':None,'luckCurrent':None,'luckTarget':None,'luckFull':False,
                     'luckText':'当前最高幸运值 — / —','baitStatus':'等待识别鱼竿与幸运值','baitDisplay':'自动补饵未开启',
                     'normalStop':False,'reconnectReady':False,'shutdownStatus':'','shutdownPending':False,'running':False,'closing':False,'canClose':False,'catchCount':0,'rodsUsed':0,
                     'status':'选择设备，进入绿色鱼竿界面后开始。',
                     'requirement':'后台/前台需要 MuMu 模拟器 · MuMuNxDevice.exe'}
        self.devicesReady.connect(self._devices_ready)
        self.timer=QTimer(self);self.timer.setInterval(75);self.timer.timeout.connect(self.poll);self.timer.start()
        if discover:QTimer.singleShot(0,self.refresh)
    @Property('QVariantMap',notify=changed)
    def state(self):return self._state.copy()
    def update(self,**values):
        if any(self._state.get(k)!=v for k,v in values.items()):
            self._state.update(values);self.changed.emit()
    def persist(self):
        values=asdict(self.settings)
        for key in values:
            if key in self._state:values[key]=self._state[key]
        values['shutdown_on_stop']=False
        try:(ROOT/'settings.json').write_text(json.dumps(values,ensure_ascii=False,indent=2),encoding='utf-8')
        except OSError:logging.exception('Settings save failed')
    @Slot(str,str)
    def draftValue(self,key,value):
        if key in ('bait_limit','rod_budget','crop_top','crop_bottom'):
            self.update(**{key:value})
    @Slot(str,'QVariant')
    def setValue(self,key,value):
        editable=('desired_multiplier','auto_bait','full_bait_protection','stop_on_bait_end','stop_when_buffs_end','bait_limit','rod_budget','crop_top','crop_bottom','ui_scale','shutdown_on_stop','shutdown_force')
        if key not in editable:return
        if key=='ui_scale':
            value=float(value)
            if value not in UI_ZOOMS:return
            self.update(ui_scale=value)
            if self.session_settings:self.session_settings.ui_scale=value
            self.persist();return
        if key=='desired_multiplier':
            value=int(value)
            if value not in (1,2,3,5,10,20,50,100):return
            self.update(desired_multiplier=value)
            if self._state['running'] and not self.cancel.is_set():
                self.session_updates.put(value)
                self.update(status=f'期望倍率已改为 x{value}，下一次抛竿前应用。')
            self.persist();return
        if key in ('bait_limit','rod_budget','crop_top','crop_bottom'):
            try: value=int(value)
            except (ValueError,TypeError): return
            if value<0:return
        changes={key:value}
        if value and key in ('auto_bait','stop_when_buffs_end'):
            changes['stop_when_buffs_end' if key=='auto_bait' else 'auto_bait']=False
        self.update(**changes)
        if key=='shutdown_on_stop' and not value:self.cancelShutdown()
        if self._state['running'] and key not in ('shutdown_on_stop','shutdown_force'):
            self.session_updates.put(changes)
            self.update(status='设置已更新；裁剪边距在待钓时应用，已提交的打窝先等待结果。')
        self.persist()
    @Slot(float)
    def resizeTo(self,factor):
        if not .5<=factor<=2.:return
        self.update(ui_scale=factor)
        if self.session_settings:self.session_settings.ui_scale=factor
    @Slot()
    def finishResize(self):self.persist()
    @Slot(int)
    def setMode(self,index):
        if index not in range(3):return
        if self._state['running']:
            self.queue_change(('mode',index));return
        self.update(modeIndex=index,mode=list(MODE_LABELS)[index]);self.refresh()
    @Slot(int)
    def selectDevice(self,index):
        if index in range(len(self.entries)):
            if self._state['running']:
                self.queue_change(('device',self.entries[index]));return
            self.update(deviceIndex=index,deviceText=self._state['devices'][index])
            if self.resume_counts is not None:self.start()
    @Slot(str)
    def setAddress(self,address):
        if self._state['running']:
            self.queue_change(('address',address));return
        self.update(deviceText=address,deviceIndex=-1)
        if self.resume_counts is not None:self.start()
    def queue_change(self, change):
        self.pending_change=change
        self.session_updates.put({'_reconnect':True})
        self.update(status='将在当前一竿或打窝完成后切换连接，本次累计保留。')
    def finish_change(self):
        change=self.pending_change;self.pending_change=None
        self.resume_counts=(self._state['catchCount'],self._state['rodsUsed'],self._state['baitUsed'])
        self.update(reconnectReady=False)
        if change[0]=='mode':
            self.resume_hwnd=getattr(self,'active_hwnd',None)
            self.setMode(change[1])
            self.update(status='已释放旧连接；正在匹配设备，必要时请选择新设备继续。')
        elif change[0]=='device':
            entry=change[1]
            self.entries.append(entry)
            self.update(devices=self._state['devices']+[entry['title']],deviceIndex=len(self.entries)-1,deviceText=entry['title'])
            self.start()
        else:self.setAddress(change[1])
    @Slot()
    def refresh(self):
        if self._state['closing']:return
        self.generation+=1;generation=self.generation;mode=self._state['mode']
        self.update(refreshing=True,requirement=('选择 ADB 设备或输入 IP:端口；通用模式不依赖 MuMu' if mode=='maatouch' else '后台/前台需要 MuMu 模拟器 · MuMuNxDevice.exe'))
        def discover():
            try:
                if mode=='maatouch':
                    from .generic_adb import discover_adb_entries
                    entries=discover_adb_entries()
                else:entries=window_details()
                self.devicesReady.emit(generation,entries,'')
            except Exception as exc:self.devicesReady.emit(generation,[],str(exc))
        threading.Thread(target=discover,daemon=True).start()
    @Slot(int,object,str)
    def _devices_ready(self,generation,entries,error):
        if generation!=self.generation or self._state['closing']:return
        old=self._state['deviceText'];self.entries=entries
        titles=[e['title'] if self._state['mode']=='maatouch' else f"{e['title']} · {e['size'][0]}×{e['size'][1]} · PID {e['pid']}" for e in entries]
        manual=self._state['mode']=='maatouch' and self._state['deviceIndex']<0 and old not in ('请选择设备','未找到设备')
        index=-1 if manual else titles.index(old) if old in titles else (0 if titles else -1)
        self.update(devices=titles,deviceIndex=index,deviceText=old if manual else titles[index] if index>=0 else '未找到设备',refreshing=False)
        if error:self.update(status=f'设备发现失败：{error}')
        if self.resume_counts is not None and self.resume_hwnd is not None:
            matching=next((i for i,e in enumerate(entries) if e.get('hwnd')==self.resume_hwnd),None)
            self.resume_hwnd=None
            if matching is not None:self.selectDevice(matching)
    def validated_settings(self):
        values={k:self._state[k] for k in asdict(Settings())}
        for key in ('desired_multiplier','bait_limit','rod_budget','crop_top','crop_bottom'):
            values[key]=int(values[key])
        if values['desired_multiplier'] not in (1,2,3,5,10,20,50,100) or min(values[k] for k in ('bait_limit','rod_budget','crop_top','crop_bottom'))<0:raise ValueError()
        return Settings(**values)
    @Slot()
    def start(self):
        if self._state['running'] or self._state['closing'] or self._state['refreshing'] or self._state['shutdownPending']:return
        index=self._state['deviceIndex']
        if self._state['mode']=='maatouch' and index<0:
            address=self._state['deviceText'].strip();adb=self.entries[0]['adb_path'] if self.entries else shutil.which('adb')
            if adb and re.fullmatch(r'[A-Za-z0-9_.:\[\]-]+',address):
                self.entries.append({'title':address,'hwnd':None,'adb_path':adb,'adb_address':address});index=len(self.entries)-1
        if index<0 or index>=len(self.entries):self.update(status='未找到目标设备，请启动模拟器并刷新。');return
        if self._state['mode']=='foreground':
            try:_,_,width,height=client_rect(self.entries[index]['hwnd'])
            except RuntimeError as exc:self.update(status=str(exc));self.warning.emit('游戏窗口无法开始',str(exc));return
            if width<315:
                self.warning.emit('游戏窗口较小',f'当前窗口为 {width}×{height}，宽度小于建议的315像素。小窗口可能导致倍率或窄黄条识别不稳定；关闭提示后仍可继续运行。')
                self.pending_start=index
                return
        self._start_worker(index)
    @Slot()
    def confirmStart(self):
        index=getattr(self,'pending_start',None);self.pending_start=None
        if index is not None and not self._state['closing'] and not self._state['running']:self._start_worker(index)
    def _start_worker(self,index):
        try:settings=self.validated_settings()
        except (ValueError,TypeError):self.update(status='请检查倍率、边距、用饵预算和用竿预算，均须为非负整数。');return
        if settings.mode=='maatouch':
            settings.adb_path=self.entries[index]['adb_path'];settings.adb_address=self.entries[index]['adb_address']
        self.settings=settings;self.update(adb_path=settings.adb_path,adb_address=settings.adb_address);self.persist()
        self.active_hwnd=self.entries[index].get('hwnd')
        counts=self.resume_counts;self.resume_counts=None;self.manual_stop=False
        self.cancel=threading.Event();self.session_updates=queue.Queue();self.session_settings=settings
        self.update(running=True,normalStop=False,reconnectReady=False,shutdownStatus="",catchCount=counts[0] if counts else 0,rodsUsed=counts[1] if counts else 0,baitDeadline=None,baitPhase=None,baitAtLimit=False,baitUsed=counts[2] if counts else 0,rodLevel=None,luckCurrent=None,luckTarget=None,baitStatus='等待识别鱼竿与幸运值',status='正在连接设备…')
        self.worker=threading.Thread(target=run,args=(self.entries[index]['hwnd'],settings,self.cancel,self.events.put,self.session_updates,self.events.put,counts),daemon=True);self.worker.start()
    @Slot()
    def stop(self):
        self.cancelShutdown()
        self.pending_start=None;self.pending_change=None;self.resume_counts=None;self.manual_stop=True
        self.cancel.set()
    @Slot()
    def closeRequested(self):
        if self._state['closing']:return
        self.cancelShutdown()
        self.manual_stop=True;self.pending_change=None;self.resume_counts=None
        self.cancel.set();self.update(closing=True,status='正在停止并释放操作…')
        self.poll()
    def poll(self):
        if self._state['closing']:
            if not self.worker or not self.worker.is_alive():
                self.update(canClose=True)
                if self.window:self.window.close()
            return
        if self.hotkeys:
            if user32.GetAsyncKeyState(STOP_KEY)&1:self.pulse.emit('stop');self.stop()
            if user32.GetAsyncKeyState(START_KEY)&1:self.pulse.emit('start');self.start()
        values={}
        while not self.events.empty():
            message=self.events.get_nowait()
            if isinstance(message,dict):
                message=dict(message)
                for key in ('luckCurrent','luckTarget'):
                    if message.get(key) is None:message.pop(key,None)
                values.update(message);continue
            values['status']=re.split(r'[｜|]',message,maxsplit=1)[0]
            catches=re.search(r'已完成\s*(\d+)\s*次',message);rods=re.search(r'本次用竿\s*(\d+)\s*/\s*(\d+|不限)',message)
            if catches:values['catchCount']=int(catches.group(1))
            if rods:values['rodsUsed']=int(rods.group(1))
        if values:self.update(**values)
        if self._state['running'] and (not self.worker or not self.worker.is_alive()):
            self.update(running=False)
            if self.pending_change and self._state['reconnectReady']:
                self.finish_change()
            else:
                self.pending_change=None
                self.handle_stopped()
        self.refresh_bait_display()
        self.tick_shutdown()
    def handle_stopped(self):
        if not self._state['shutdown_on_stop'] or not self._state['normalStop'] or self.manual_stop or self._state['closing']:
            return
        if self._state['shutdownPending']:return
        self.shutdown_deadline=time.monotonic()+15
        self.update(normalStop=False,shutdownPending=True,shutdownStatus='15 秒后关机')
        self.alert_shutdown()
    def alert_shutdown(self):
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            logging.exception('Shutdown notification sound failed')
        if self.window is not None:
            try:
                self.shutdown_window_was_topmost=bool(self.window.flags() & Qt.WindowStaysOnTopHint)
                self.window.setFlag(Qt.WindowStaysOnTopHint,True)
                self.window.showNormal()
                self.window.raise_()
                self.window.requestActivate()
            except Exception:
                logging.exception('Could not bring shutdown countdown to front')
    def restore_shutdown_window(self):
        if self.shutdown_window_was_topmost is not None:
            try:
                if self.window is not None:self.window.setFlag(Qt.WindowStaysOnTopHint,self.shutdown_window_was_topmost)
            except Exception:
                logging.exception('Could not restore window stacking')
            finally:
                self.shutdown_window_was_topmost=None
    @Slot()
    def cancelShutdown(self):
        if self._state['shutdownPending']:
            self.shutdown_deadline=None
            self.update(shutdownPending=False,normalStop=False,shutdownStatus='已取消本次关机')
            self.restore_shutdown_window()
    def tick_shutdown(self):
        if not self._state['shutdownPending']:return
        if not self._state['shutdown_on_stop'] or self.manual_stop or self._state['closing']:
            self.cancelShutdown();return
        remaining=max(0,math.ceil(self.shutdown_deadline-time.monotonic()))
        if remaining:
            self.update(shutdownStatus=f'{remaining} 秒后关机');return
        self.shutdown_deadline=None
        self.update(shutdownPending=False,shutdownStatus='正在请求关机…')
        self.restore_shutdown_window()
        try:
            from .shutdown import request_shutdown
            request_shutdown(bool(self._state['shutdown_force']))
            self.update(shutdownStatus='已发送关机请求')
        except Exception as exc:
            logging.exception('Shutdown request failed')
            self.update(shutdownStatus='关机请求失败，请手动关机。',status=f'关机请求失败：{exc}')
    def refresh_bait_display(self):
        state=self._state
        current,target=state['luckCurrent'],state['luckTarget']
        full=current is not None and target is not None and current==target
        luck=f"当前最高幸运值 {current if current is not None else '—'} / {target if target is not None else '—'}"
        if full:luck+=' · 已满'
        elif current is not None and target is None:luck+=' · 待识别鱼竿'
        elif current is not None and not target-4<=current<=target:luck+=' · 待读数确认'
        elif current is not None:luck+=' · 待补充'
        label=state['baitStatus']
        if not state['running']:
            label='自动补饵未开启' if not state['auto_bait'] else '待启动 · 自动识别后维持满饵'
        elif state['baitDeadline'] is not None and not state['baitPhase'] and label.startswith('等待补饵'):
            seconds=max(0,math.ceil(state['baitDeadline']-time.monotonic()))
            label=f'等待补饵 · {seconds} 秒后尝试，恢复满额则取消' if seconds else '重新检查幸运值与鱼饵库存'
        self.update(luckText=luck,luckFull=full,baitDisplay=label)


class GpuApp:
    def __init__(self,discover=True,hotkeys=True,animate_startup=False):
        self.application=QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        self.application.setApplicationName('TaTaAutoFish')
        self.application.setWindowIcon(QIcon(str(ASSETS/'app.ico')))
        from .startup import configure_graphics
        configure_graphics()
        self.font_ids=[]
        for weight in ('500M','700B','900H'):
            value=QFontDatabase.addApplicationFont(str(ASSETS/'fonts'/f'ChironGoRoundTC-{weight}.ttf'))
            if value<0:raise RuntimeError('无法加载界面字体')
            self.font_ids.append(value)
        self.backend=Backend(discover,hotkeys)
        self.engine=QQmlApplicationEngine()
        self.qml_errors=[]
        self.engine.warnings.connect(lambda errors:self.qml_errors.extend(e.toString() for e in errors))
        self.engine.rootContext().setContextProperty('animateStartup',animate_startup)
        from autotata.popup_windows import PopupWindows
        self.popup_windows=PopupWindows(self.application)
        self.engine.rootContext().setContextProperty('popupWindows',self.popup_windows)
        self.engine.rootContext().setContextProperty('backend',self.backend)
        self.engine.rootContext().setContextProperty('assetBase',QUrl.fromLocalFile(str(ASSETS.resolve())+'/').toString())
        self.engine.load(QUrl.fromLocalFile(str(ASSETS/'ui/Main.qml')))
        if not self.engine.rootObjects():raise RuntimeError('界面加载失败：'+str(self.qml_errors))
        self.window=self.engine.rootObjects()[0];self.backend.window=self.window
        from autotata.window_frame import WindowFrame
        self.window_frame=WindowFrame(self.window)
        self.window.setIcon(QIcon(str(ASSETS/'ui/rod-wood.png')))
        from .startup import center_window
        center_window(self.window)
        self.window.sceneGraphInitialized.connect(self.log_renderer,Qt.ConnectionType.QueuedConnection)
    def log_renderer(self):
        logging.info('GPU UI graphics API=%s samples=%s',self.window.rendererInterface().graphicsApi(),self.window.format().samples())
    def exec(self):return self.application.exec()

def main():
    from .log_policy import configure_logging
    maintenance=configure_logging()
    try:
        app=GpuApp();app.exec()
    finally:
        logging.shutdown()
        maintenance.close()
