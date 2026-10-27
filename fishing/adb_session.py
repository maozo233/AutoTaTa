"""MuMu device capture and MaaTouch input, independent of desktop coordinates."""
import logging
import time
import json
import re
import subprocess
from pathlib import Path
from .maa_input import initialize, wait_job
from .windows import process_id, process_name, process_path, user32
from .hotkeys import STOP_KEY


def discover_mumu_device(hwnd=None):
    initialize()
    # Prefer the selected MuMu install's own config and ADB. Scanning every ADB
    # installation can restart the shared server with an incompatible version.
    if hwnd is not None:
        executable=process_path(process_id(hwnd))
        if executable:
            for root in Path(executable).parents:
                adb=root/'nx_main/adb.exe'
                if not adb.exists():continue
                configs=list((root/'vms').glob('MuMuPlayer-*/configs/vm_config.json'))
                if len(configs)>1:
                    raise RuntimeError('该MuMu安装有多个实例配置，无法确定目标设备，请使用前台模式。')
                if len(configs)==1:
                    vm=configs[0].parent.parent.name
                    match=re.fullmatch(r'MuMuPlayer-[0-9.]+-(\d+)',vm)
                    try:
                        port=int(json.loads(configs[0].read_text(encoding='utf-8'))['vm']['nat']['port_forward']['adb']['host_port'])
                    except (OSError,ValueError,KeyError,TypeError):break
                    if match and 0<port<65536:
                        from maa.toolkit import AdbDevice
                        return AdbDevice(vm,adb,f'127.0.0.1:{port}',64,4,
                                         {'extras':{'mumu':{'enable':True,'index':int(match[1]),'path':root.as_posix()}}})
                break
    from maa.toolkit import Toolkit
    devices=[device for device in Toolkit.find_adb_devices()
             if device.config.get('extras',{}).get('mumu',{}).get('enable')]
    if not devices:
        raise RuntimeError('未找到 MuMu 的 ADB 连接，请启动 MuMu 并检查 ADB 是否开启。')
    if len(devices)!=1:
        raise RuntimeError('发现多个 MuMu 实例，暂不能自动确定目标；请只保留一个 MuMu 实例后重新开始。')
    return devices[0]


class AdbSession:
    def __init__(self, hwnd, cancel, mode="maatouch", vision_factory=None, allow_active=False):
        self.hwnd,self.cancel=hwnd,cancel
        if mode not in ("maatouch", "mumu_sdk"):
            raise ValueError("Unsupported device input mode")
        self.input_name = "MuMu SDK" if mode == "mumu_sdk" else "MaaTouch"
        self.mode = mode
        self.vision_factory = vision_factory
        self.allow_active = allow_active
        self.display_binding = None
        self.pid=process_id(hwnd)
        self.controller=None
        self.size=None
        self.latest=None
        self.sequence=0
        self.closed=False
        self.fallback_session=None
        self.log=logging.getLogger('fishing')

    def wait(self, job, timeout):
        deadline=time.monotonic()+timeout
        while not job.done:
            if self.cancel.is_set() or user32.GetAsyncKeyState(STOP_KEY)&0x8000:
                self.cancel.set()
                raise RuntimeError('已收到停止指令。')
            if time.monotonic()>deadline:
                raise RuntimeError('后台 ADB 操作超时，已停止。')
            time.sleep(.005)
        if not job.succeeded:
            raise RuntimeError('后台操作失败，请检查设备连接后重新开始。')

    def validate(self):
        if self.cancel.is_set():return False
        if process_id(self.hwnd)!=self.pid or process_name(self.pid).lower()!='mumunxdevice.exe':
            raise RuntimeError('目标 MuMu 进程已改变，已停止。')
        return True

    def start(self):
        if not self.validate():return
        from maa.controller import AdbController
        from maa.define import MaaAdbScreencapMethodEnum as Capture, MaaAdbInputMethodEnum as Input
        device=discover_mumu_device(self.hwnd)
        self.device=device
        if not self.validate():return
        try:
            connected=subprocess.run([str(device.adb_path),'connect',device.address],
                                     stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                     timeout=8,creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise RuntimeError('MuMu ADB连接失败，请检查模拟器和ADB设置。') from exc
        if connected.returncode or b'connected to' not in connected.stdout.lower():
            raise RuntimeError('无法连接MuMu的ADB端口，请检查ADB是否开启。')
        from .display_probe import inspect_fishing_displays, SdkCaptureUnavailable
        try:
            config,target=inspect_fishing_displays(device,vision_factory=self.vision_factory,allow_active=self.allow_active) if self.vision_factory else inspect_fishing_displays(device)
        except SdkCaptureUnavailable:
            if self.mode!='mumu_sdk' or not self.validate():raise
            self.activate_fallback('MuMuSDK显示区截图失败')
            return
        self.display_binding=target
        if self.mode == "maatouch":
            from .maatouch_display import prepare_maatouch_display
            from types import SimpleNamespace
            bound_device=SimpleNamespace(adb_path=device.adb_path,address=device.address,config=config)
            config,target=prepare_maatouch_display(bound_device,binding=target)
            self.display_binding=target
            self.log.info('MaaTouch display binding display_id=%s resolution=%sx%s orientation=visible',*target)
        self.controller=AdbController(device.adb_path,device.address,
                                      screencap_methods=Capture.EmulatorExtras,
                                      input_methods=Input.EmulatorExtras if self.mode == "mumu_sdk" else Input.Maatouch,config=config)
        if not self.controller.set_screenshot_use_raw_size(True):
            raise RuntimeError('MuMu 设备原始坐标设置失败。')
        self.wait(self.controller.post_connection(),30)
        try:
            self.wait(self.controller.post_screencap(),8)
        except RuntimeError:
            if self.mode!='mumu_sdk' or not self.validate():raise
            self.size=tuple(target[1:])
            self.activate_fallback('MuMuSDK首次截图失败')
            return
        self.size=tuple(self.controller.resolution)
        if target and self.size != target[1:]:
            raise RuntimeError("MaaTouch 触摸显示区尺寸与截图不一致，已停止。")
        if self.size[0]>=self.size[1]:
            raise RuntimeError('请将 MuMu 游戏设为竖屏后重新开始。')
        self.log.info('%s connected address=%s device_resolution=%s capture=EmulatorExtras',self.input_name,device.address,self.size)

    def activate_fallback(self, reason):
        if self.mode!='mumu_sdk':raise RuntimeError(reason)
        if not self.validate():raise RuntimeError('已收到停止指令。')
        if self.fallback_session is not None:return self.fallback_session
        from .generic_adb import GenericAdbSession
        from .engine import Settings
        fallback_settings=Settings(adb_path=str(self.device.adb_path),adb_address=self.device.address)
        replacement=GenericAdbSession(fallback_settings,self.cancel,vision_factory=self.vision_factory) if self.vision_factory else GenericAdbSession(fallback_settings,self.cancel)
        try:
            if self.display_binding is None:
                replacement.start(allow_active=True)
            else:
                replacement.start_verified(self.display_binding)
                expected=self.size or tuple(self.display_binding[1:])
                if replacement.size!=expected:raise RuntimeError('ADB回退显示区尺寸不一致')
        except Exception:
            replacement.close();raise
        self.fallback_session=replacement
        self.size=replacement.size
        self.display_binding=replacement.display_binding
        self.fallback_reason=reason
        self.log.warning('SDK fallback reason=%s display=%s foreground=%s',reason,self.display_binding,user32.GetForegroundWindow())
        return replacement

    def read(self):
        if not self.validate():return self.latest
        if self.fallback_session is not None:
            sample=self.fallback_session.read()
            if sample is not None:
                frame,captured_at,_,size=sample
                self.sequence+=1
                self.latest=(frame,captured_at,self.sequence,size)
            return self.latest
        try:
            self.wait(self.controller.post_screencap(),4)
            frame=self.controller.cached_image
            if frame is None or getattr(frame,'size',0)==0:
                raise RuntimeError('MuMuSDK返回空截图')
        except RuntimeError:
            if self.mode!='mumu_sdk' or not self.validate():raise
            self.activate_fallback('MuMuSDK截图失败或超时')
            return self.read()
        size=(frame.shape[1],frame.shape[0])
        if size!=self.size:raise RuntimeError('模拟器内部游戏分辨率已变化，请重新开始。')
        self.sequence+=1
        self.latest=(frame,time.monotonic(),self.sequence,size)
        return self.latest

    def click(self, point):
        if not self.validate():return
        if self.fallback_session is not None:return self.fallback_session.click(point)
        x,y=map(round,point)
        if not (0<=x<self.size[0] and 0<=y<self.size[1]):
            raise RuntimeError('后台目标坐标超出游戏画面，已停止。')
        self.log.info('%s click submitted device=(%s,%s)',self.input_name,x,y)
        self.wait(self.controller.post_click(x,y),3)
        self.log.info('%s click completed device=(%s,%s)',self.input_name,x,y)

    def fallback_click(self, point):
        if not self.validate():return
        x,y=map(round,point)
        if not (0<=x<self.size[0] and 0<=y<self.size[1]):raise RuntimeError('ADB回退坐标越界')
        display=self.display_binding[0] if self.display_binding else 0
        device=getattr(self,'device',None)
        adb=str(device.adb_path) if device else self.settings.adb_path
        address=device.address if device else self.settings.adb_address
        command=[adb,'-s',address,'shell','input','-d',str(display),'tap',str(x),str(y)]
        result=subprocess.run(command,capture_output=True,timeout=3,creationflags=subprocess.CREATE_NO_WINDOW)
        self.log.info('SDK cast fallback ADB display=%s point=(%s,%s) exit=%s foreground=%s',display,x,y,result.returncode,user32.GetForegroundWindow())
        if result.returncode:raise RuntimeError('抛竿ADB回退失败：'+result.stderr.decode(errors='replace')[:200])

    def close(self):
        if self.closed:return
        self.closed=True
        try:
            if self.fallback_session:self.fallback_session.close()
        finally:
            self.fallback_session=None
            if self.controller:wait_job(self.controller.post_inactive(),timeout=3)
