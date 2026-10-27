"""Generic ADB + patched MaaTouch path. No emulator SDK calls or configs."""
import hashlib
import subprocess
import shutil
import re
from .paths import ASSETS
from .adb_session import AdbSession
from .display_probe import parse_displays,choose_fishing_display
from .maa_input import initialize
import cv2
import numpy as np

def decode_adb_png(payload):
    # Older ADB shell transports insert CR before every LF, even in exec-out.
    if payload.startswith(b"\x89PNG\r\r\n"):
        payload=payload.replace(b"\r\n",b"\n")
    return cv2.imdecode(np.frombuffer(payload,np.uint8),cv2.IMREAD_COLOR) if payload else None

def adb_version_supported(path):
    try:
        result=subprocess.run([str(path),'version'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=4,creationflags=subprocess.CREATE_NO_WINDOW)
        match=re.search(rb'Android Debug Bridge version (\d+)\.(\d+)\.(\d+)',result.stdout)
        return result.returncode==0 and match is not None and tuple(map(int,match.groups())) >= (1,0,41)
    except (OSError,subprocess.TimeoutExpired):return False

def discover_adb_entries():
    initialize()
    from maa.toolkit import Toolkit
    entries=[];seen=set()
    preferred=shutil.which("adb")
    if preferred and not adb_version_supported(preferred):preferred=None
    versions={}
    for device in Toolkit.find_adb_devices(specified_adb=preferred):
        path=str(device.adb_path)
        if path not in versions:versions[path]=adb_version_supported(path)
        if not versions[path]:continue
        key=(str(device.adb_path),device.address)
        if key in seen:continue
        seen.add(key)
        entries.append({'title':f'ADB · {device.address}','adb_path':str(device.adb_path),'adb_address':device.address,'hwnd':None})
    return entries

class GenericAdbSession(AdbSession):
    def __init__(self,settings,cancel,vision_factory=None):
        super().__init__(0,cancel,mode='maatouch',vision_factory=vision_factory)
        self.stream=None
        self.settings=settings;self.input_name='ADB + MaaTouch';self.remote=None
    def validate(self):return not self.cancel.is_set()
    def command(self,*args,timeout=8):
        result=subprocess.run([self.settings.adb_path,'-s',self.settings.adb_address,*args],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:raise RuntimeError('ADB 操作失败：'+result.stderr.decode('utf-8',errors='replace')[:180])
        return result.stdout
    def snapshot_command(self,display):
        return f'env CLASSPATH={self.remote} app_process /data/local/tmp com.tata.autofish.Snapshot {int(display)}'
    def snapshot(self,display):
        try:
            payload=self.command('exec-out',self.snapshot_command(display))
            return decode_adb_png(payload)
        except (RuntimeError,cv2.error):return None
    def start(self,allow_active=False):
        initialize()
        if not self.validate():return
        if not self.settings.adb_path or not self.settings.adb_address:raise RuntimeError('请选择已连接的 ADB 设备。')
        if not adb_version_supported(self.settings.adb_path):raise RuntimeError('ADB 版本过旧或不可用，请使用 1.0.41 或更高版本后刷新。')
        if re.fullmatch(r'[A-Za-z0-9_.:\[\]-]+:\d+',self.settings.adb_address):
            connection=subprocess.run([self.settings.adb_path,'connect',self.settings.adb_address],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=8,creationflags=subprocess.CREATE_NO_WINDOW)
            if connection.returncode or b'connected to' not in connection.stdout.lower():
                raise RuntimeError('ADB TCP 连接失败，请刷新并检查设备地址。')
        asset=ASSETS/'maatouch-display.dex'
        self.remote='/data/local/tmp/tata-maatouch-'+hashlib.sha256(asset.read_bytes()).hexdigest()[:16]+'.dex'
        self.command('push',str(asset),self.remote)
        displays=parse_displays(self.command('shell','dumpsys window displays').decode('utf-8',errors='replace'))
        if not displays:raise RuntimeError('ADB 无法解析显示区；未发送触摸。')
        frames=[(i,self.snapshot(i)) for i in sorted(displays)]
        self.default_capture=False
        if all(frame is None for _,frame in frames) and set(displays)=={0}:
            # Older Android: physical default display only, never guess a virtual ID.
            payload=self.command('exec-out','screencap -p')
            frames=[(0,decode_adb_png(payload))]
            self.default_capture=True
        display,width,height,multiplier=choose_fishing_display(frames,allow_active=allow_active,vision_factory=self.vision_factory) if self.vision_factory else choose_fishing_display(frames,allow_active=allow_active)
        self.connect_display(display,width,height,multiplier)

    def start_verified(self,binding):
        # Binding comes from this session's already verified game display.
        initialize()
        asset=ASSETS/'maatouch-display.dex'
        self.remote='/data/local/tmp/tata-maatouch-'+hashlib.sha256(asset.read_bytes()).hexdigest()[:16]+'.dex'
        self.command('push',str(asset),self.remote)
        self.default_capture=False
        self.connect_display(*binding,None)

    def connect_display(self,display,width,height,multiplier):
        self.display_binding=(display,width,height)
        shell=['{ADB}','-s','{ADB_SERIAL}','shell']
        config={'command':{
            'Resolution':shell+[f'echo {width} {height} 0'],
            'Orientation':shell+['echo 0'],
            'InvokeApp':shell+[f'stty raw -echo 2>/dev/null; export CLASSPATH="{self.remote}:/data/local/tmp/{{APP_WORKING_FILE}}"; app_process /data/local/tmp {{PACKAGE_NAME}} {display}'],
            'ScreencapEncode':['{ADB}','-s','{ADB_SERIAL}','exec-out','screencap -p' if self.default_capture else self.snapshot_command(display)]}}
        if not self.validate():return
        from maa.controller import AdbController
        from maa.define import MaaAdbScreencapMethodEnum as S,MaaAdbInputMethodEnum as I
        self.controller=AdbController(self.settings.adb_path,self.settings.adb_address,screencap_methods=S.Encode,input_methods=I.Maatouch,config=config)
        if not self.controller.set_screenshot_use_raw_size(True):raise RuntimeError('ADB 原始坐标设置失败。')
        self.wait(self.controller.post_connection(),30);self.wait(self.controller.post_screencap(),8)
        self.size=tuple(self.controller.resolution)
        if self.size!=(width,height):raise RuntimeError('ADB 截图与触摸显示区尺寸不一致；已停止。')
        if not self.default_capture:
            from .adb_stream import AdbFrameStream
            self.stream=AdbFrameStream(self.settings.adb_path,self.settings.adb_address,self.remote,self.cancel)
        self.log.info('Generic MaaTouch display verified address=%s display_id=%s size=%s multiplier=%s capture=Android no_emulator_sdk=True',self.settings.adb_address,display,self.size,multiplier)

    def read(self):
        if self.stream is None:return super().read()
        if not self.validate():return self.latest
        frame,captured_at=self.stream.read(self.display_binding[0])
        size=(frame.shape[1],frame.shape[0])
        if size!=self.size:raise RuntimeError('ADB 游戏分辨率已变化，已停止。')
        self.sequence+=1;self.latest=(frame,captured_at,self.sequence,size)
        return self.latest
    def close(self):
        try:
            if self.stream:self.stream.close()
        finally:
            self.stream=None
            super().close()
