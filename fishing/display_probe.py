"""Select a unique fishing display by pixels before any input is initialized."""
import ctypes as C
import copy
import logging
import re
import subprocess
import cv2
import numpy as np
from .vision import Vision


def parse_displays(text):
    parts=re.split(r'Display:\s*mDisplayId=(\d+)',text)
    result={}
    for i in range(1,len(parts),2):
        block=parts[i+1]
        match=re.search(r'mCurrentFocus=Window\{[^\n}]*?\s([a-zA-Z0-9_.]+)/',block)
        if not match:match=re.search(r'mFocusedApp=ActivityRecord\{[^\n}]*?\s([a-zA-Z0-9_.]+)/',block)
        result[int(parts[i])]=match.group(1) if match else None
    return result

class SdkCaptureUnavailable(RuntimeError):
    pass


class DisplayProbe:
    def __init__(self,device):
        extras=device.config.get('extras',{}).get('mumu',{})
        if not extras.get('enable'):raise RuntimeError('未配置 MuMu 显示区查询接口。')
        self.root=extras['path'];self.index=int(extras['index'])
        from pathlib import Path
        self.dll=C.CDLL(str(Path(self.root)/'nx_main/sdk/external_renderer_ipc.dll'))
        self.connect=self.dll.nemu_connect;self.connect.argtypes=[C.c_wchar_p,C.c_int];self.connect.restype=C.c_int
        self.disconnect=self.dll.nemu_disconnect;self.disconnect.argtypes=[C.c_int];self.disconnect.restype=None
        self.identify=self.dll.nemu_get_display_id;self.identify.argtypes=[C.c_int,C.c_char_p,C.c_int];self.identify.restype=C.c_int
        self.capture=self.dll.nemu_capture_display;self.capture.argtypes=[C.c_int,C.c_int,C.c_int,C.POINTER(C.c_int),C.POINTER(C.c_int),C.c_void_p];self.capture.restype=C.c_int
        self.handle=self.connect(self.root,self.index)
        if not self.handle:raise RuntimeError('无法连接 MuMu 显示区查询接口。')
    def read(self,display):
        width,height=C.c_int(),C.c_int()
        if self.capture(self.handle,display,0,C.byref(width),C.byref(height),None)!=0:return None
        w,h=width.value,height.value
        if not (0<w<=8192 and 0<h<=8192):return None
        pixels=np.empty((h,w,4),np.uint8)
        if self.capture(self.handle,display,pixels.nbytes,C.byref(width),C.byref(height),pixels.ctypes.data)!=0:return None
        if (width.value,height.value)!=(w,h):return None
        return cv2.flip(cv2.cvtColor(pixels,cv2.COLOR_RGBA2BGR),0)
    def close(self):
        if self.handle:self.disconnect(self.handle);self.handle=0

def choose_fishing_display(frames,allow_active=False,vision_factory=None):
    if vision_factory is not None:
        return choose_feature_display(frames,vision_factory,allow_active)
    matches=[]
    for display,frame in frames:
        if frame is None:continue
        try:
            vision=Vision();obs=vision.observe(frame)
            if obs.state=='ready' or (allow_active and obs.state in ('waiting','hook','fight','purple_wait','result')):matches.append((display,frame,vision))
        except RuntimeError:continue
    if not matches:raise RuntimeError('各显示区均未找到绿色鱼竿钓鱼界面；未发送操作，请进入钓鱼界面后重新开始。')
    if len(matches)!=1:raise RuntimeError('多个显示区同时匹配钓鱼界面；未发送操作，请只保留一个目标游戏。')
    display,frame,vision=matches[0]
    value=vision.read_multiplier(vision.normalize(frame)) if vision.observe(frame).state=='ready' else None
    if value is None and not allow_active:raise RuntimeError('目标显示区倍率不清晰；未发送操作。')
    return display,frame.shape[1],frame.shape[0],value

def choose_feature_display(frames,vision_factory,allow_active=False):
    """Opt-in feature recognizer; default fishing verification is unchanged."""
    matches=[]
    for display,frame in frames:
        if frame is None:continue
        try:
            vision=vision_factory();obs=vision.observe(frame)
            if obs.state=='ready' or (allow_active and (obs.state in ('choice','reward','cardpack','confirm','transition','panel','capsule_group','purchase') or
                                                      (obs.state=='reward_button' and obs.reward_context))):
                matches.append((display,frame,obs))
        except RuntimeError:continue
    if len(matches)!=1:
        raise RuntimeError('未找到唯一的目标活动画面；未发送操作，请进入转盘页面后重新开始。')
    display,frame,obs=matches[0]
    if obs.state=='ready' and obs.multiplier is None and not allow_active:
        raise RuntimeError('目标活动倍率不清晰；未发送操作。')
    return display,frame.shape[1],frame.shape[0],obs.multiplier


def inspect_fishing_displays(device,vision_factory=None,allow_active=False):
    result=subprocess.run([str(device.adb_path),'-s',device.address,'shell','dumpsys window displays'],
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=8,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise RuntimeError('无法枚举模拟器显示区；未发送操作。')
    displays=parse_displays(result.stdout.decode('utf-8',errors='replace'))
    if not displays:raise RuntimeError('无法解析模拟器显示区；未发送操作。')
    probe=DisplayProbe(device)
    try:
        frames=[(i,probe.read(i)) for i in sorted(displays)]
        if all(frame is None for _,frame in frames):
            raise SdkCaptureUnavailable('MuMuSDK未返回任何显示区截图')
        selected=choose_fishing_display(frames,vision_factory=vision_factory,allow_active=allow_active) if vision_factory else choose_fishing_display(frames)
        display,width,height,value=selected
        package=displays[display]
        if not package or probe.identify(probe.handle,package.encode(),0)!=display:
            raise RuntimeError('钓鱼画面已找到，但无法绑定同一应用显示区；未发送操作。')
    finally:probe.close()
    config=copy.deepcopy(device.config)
    config['extras']['mumu']['app_package']=package
    config['extras']['mumu']['app_cloned_index']=0
    logging.getLogger('fishing').info('Fishing display verified display_id=%s size=%sx%s package=%s multiplier=%s candidates=%s',display,width,height,package,value,sorted(displays))
    return config,(display,width,height)
