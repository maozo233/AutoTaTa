"""Use the proven fishing capture/input transports with fresh-frame checks."""
import logging
import queue
import time
import cv2
import json
from autotata.paths import ROOT
from fishing.windows import WindowCapture, Mouse, FocusLost, user32
from fishing.hotkeys import STOP_KEY
from .engine import Engine
from .vision import Vision
from .inventory import InventoryReader
from .controls import ControlReader
from .trace import Trace


def connect(hwnd, settings, cancel):
    capture = mouse = None
    try:
        if settings.mode == 'maatouch':
            from fishing.generic_adb import GenericAdbSession
            capture = mouse = GenericAdbSession(settings, cancel, vision_factory=lambda: Vision(settings.crop_top, settings.crop_bottom))
            capture.start(allow_active=True)
        elif settings.mode == 'mumu_sdk':
            from fishing.adb_session import AdbSession
            capture = mouse = AdbSession(hwnd, cancel, mode=settings.mode, vision_factory=lambda: Vision(settings.crop_top, settings.crop_bottom), allow_active=True)
            capture.start()
        else:
            capture = WindowCapture(hwnd)
            capture.start()
            mouse = Mouse(hwnd, settings.mode, cancel)
        return capture, mouse
    except Exception:
        for session in (mouse, capture if capture is not mouse else None):
            if session is not None:
                session.close()
        raise


def number_samples(vision, frame, obs):
    """Only the controls that determine cost/free status invalidate ready OCR."""
    if obs.state != 'ready' or obs.button is None:
        return None
    game = vision.normalize(frame)
    left, top, right, _ = vision.rect
    scale = 540/(right-left)
    bx, by = (obs.button[0]-left)*scale, (obs.button[1]-top)*scale
    my = by-177
    boxes = ((420, my-20, 515, my+35),)
    samples = []
    for x0,y0,x1,y1 in boxes:
        roi = game[max(0,int(y0)):min(game.shape[0],int(y1)),max(0,int(x0)):min(540,int(x1))]
        if roi.size == 0:
            return None
        samples.append(cv2.resize(roi,(64,24),interpolation=cv2.INTER_AREA))
    return {'images':samples,'free':vision.button_free(game,bx,by)}


def same_number_samples(previous, current):
    return previous is not None and current is not None and previous['free']==current['free'] and all(
        cv2.absdiff(a,b).mean() < .35 for a,b in zip(previous['images'],current['images']))


class FrameRecovery:
    def __init__(self):
        self.started = None

    def check(self, now):
        if self.started is None:
            self.started = now
        elapsed = now-self.started
        return min(3,int(elapsed/3)+1), elapsed >= 9

    def reset(self):
        self.started = None


def recovery_snapshot(frame, engine, obs, message, log):
    try:
        folder=ROOT/'logs';folder.mkdir(parents=True,exist_ok=True)
        if frame is not None:
            ok,pixels=cv2.imencode('.png',frame)
            if ok:pixels.tofile(folder/'rafting-last-recovery.png')
        values={'message':message,'hasFrame':frame is not None,'rounds':engine.completed,'used':engine.used,
                'spinAttempts':engine.spin_retries+1,'progressSeen':engine.progress_seen,
                'initialStock':engine.round_stock,'initialFree':engine.round_free,
                'state':obs.state if obs else None,'stock':obs.stock if obs else None,
                'free':obs.free if obs else None,'motion':obs.motion if obs else None,
                'choices':[reward for reward,_ in obs.choices] if obs else []}
        values.update(ambiguousChange=engine.ambiguous_change,unchangedReads=engine.unchanged_reads,
                      initialPose=engine.round_pose,currentPose=obs.wheel_pose if obs else None,
                      capsuleLabel=obs.capsule_label if obs else '',rewardContext=engine.after_choice)
        (folder/'rafting-last-recovery.json').write_text(json.dumps(values,ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception:
        log.exception('Could not save rafting recovery evidence')


def run(hwnd, settings, cancel, publish, updates):
    capture = mouse = None
    engine = Engine(settings)
    vision = Vision(settings.crop_top, settings.crop_bottom)
    inventory = InventoryReader()
    controls = ControlReader(settings.crop_top,settings.crop_bottom)
    trace = Trace()
    log = logging.getLogger('rafting')
    normal_stop = False
    try:
        publish({'status': '正在连接漂流设备…'})
        capture, mouse = connect(hwnd, settings, cancel)
        publish({'status': '设备已连接，正在识别漂流画面…'})
        recovery = FrameRecovery()
        recovery_status = None
        last_seq = -1
        last_captured = None
        status = None
        decision = None
        while not cancel.wait(.06):
            if user32.GetAsyncKeyState(STOP_KEY) & 0x8000:
                break
            while True:
                try:
                    engine.update(updates.get_nowait())
                except queue.Empty:
                    break
            read_error = ''
            try:
                sample = capture.read()
            except RuntimeError as exc:
                if cancel.is_set():break
                if not any(word in str(exc) for word in ('截图','后台操作失败','后台 ADB 操作超时')):
                    raise
                sample = None
                read_error = str(exc)
            now = time.monotonic()
            if sample is not None:
                frame, captured_at, seq, size = sample
            if sample is not None and size != mouse.size:
                raise RuntimeError('游戏画面尺寸已变化，请重新开始')
            if sample is None or now-captured_at > 1.5:
                engine.ready_at = None
                if engine.active_round and not engine.progress_seen:
                    # The missing interval could contain a whole spin. Recover
                    # observation, but don't repeat input without its history.
                    engine.ambiguous_change = True
                    engine.unchanged_at = engine.unchanged_last = None
                    engine.unchanged_reads = 0
                attempt, expired = recovery.check(now)
                if expired:
                    recovery_snapshot(frame if sample is not None else None,engine,None,'获取画面连续三次未恢复',log)
                    raise RuntimeError('画面仍未更新，已停止；请恢复模拟器后重新开始')
                message=f'画面尚未更新，重新获取 {attempt}/3'
                if message != recovery_status:
                    log.warning('capture recovery attempt=%s error=%s',attempt,read_error or 'missing/stale frame')
                    publish({'status':message})
                    recovery_status=message
                continue
            if seq == last_seq:
                continue
            recovery.reset()
            recovery_status = None
            last_seq = seq
            if (last_captured is not None and captured_at-last_captured>1.5 and
                engine.active_round and not engine.progress_seen):
                engine.ambiguous_change=True
                engine.unchanged_at=engine.unchanged_last=None
                engine.unchanged_reads=0
                log.warning('Observation gap %.2fs; suppressing ambiguous input retry',captured_at-last_captured)
            last_captured=captured_at
            if settings.mode == 'foreground' and user32.GetForegroundWindow() != hwnd:
                publish({'status': '游戏不在前台，已暂停；切回游戏后继续'})
                engine.ready_at = None
                continue
            obs = vision.observe(frame, read_numbers=False, read_inventory=False)
            if obs.multiplier is None or obs.state in ('unknown','transition'):
                obs = controls.sample(vision,frame,obs,time.monotonic())
            if time.monotonic()-captured_at > .8:
                # OCR initialization can be slow. Reuse it only after a fresh
                # frame confirms the same image; never click the old capture.
                engine.observe_progress(obs, captured_at)
                log.info('recognition frame skipped age=%.2f state=%s motion=%s stock=%s numbers_fresh=%s',
                         time.monotonic()-captured_at, obs.state, obs.motion, obs.stock, obs.numbers_fresh)
                continue
            if cancel.is_set():
                break
            while True:
                try:
                    engine.update(updates.get_nowait())
                except queue.Empty:
                    break
            action = engine.step(obs, time.monotonic())
            trace.add(frame,obs,engine,action,captured_at,time.monotonic())
            key = (obs.state, action.kind, action.message)
            if key != decision:
                elapsed = time.monotonic()
                log.info('decision=%s state=%s motion=%s active=%s rounds=%s round_age=%.2f stable_age=%.2f choices=%s',
                         action.message, obs.state, obs.motion, engine.active_round, engine.completed,
                         elapsed-engine.round_at if engine.active_round else 0.,
                         elapsed-engine.ready_at if engine.ready_at is not None else 0.,
                         [reward for reward,_ in obs.choices])
                decision = key
            stock_display = inventory.sample(vision,frame,obs,time.monotonic())
            values = {'status': action.message, 'phase': obs.state, 'rounds': engine.completed,
                      'used': engine.used, 'currentMultiplier': obs.multiplier,
                      'stock': stock_display, 'maximum': obs.maximum}
            if values != status:
                publish(values)
                status = values
            if action.kind == 'stop':
                if action.purpose!='auto_stop':trace.save(action.message)
                if action.purpose != 'auto_stop':recovery_snapshot(frame,engine,obs,action.message,log)
                normal_stop = action.purpose == 'auto_stop'
                break
            if action.kind == 'click':
                log.info('state=%s purpose=%s point=%s multiplier=%s stock=%s free=%s choices=%s', obs.state, action.purpose, action.point, obs.multiplier, obs.stock, obs.free, obs.choices)
                try:
                    if time.monotonic()-captured_at > .8:
                        log.info('Click deferred until a fresh frame purpose=%s',action.purpose)
                        continue
                    mouse.click(action.point)
                    if not cancel.is_set():
                        engine.acknowledge(action, time.monotonic(), 0 if obs.free else obs.multiplier,
                                           free=obs.free, visual_signature=obs.visual_signature,
                                           wheel_pose=obs.wheel_pose)
                        if action.purpose == 'spin_retry':recovery_snapshot(frame,engine,obs,action.message,log)
                except FocusLost as exc:
                    engine.ready_at = None
                    publish({'status': str(exc)})
    except Exception as exc:
        log.exception('Rafting session stopped')
        publish({'status': f'已停止：{exc}'})
    finally:
        inventory.close()
        controls.close()
        normal_stop = normal_stop and not cancel.is_set()
        cancel.set()
        for session in (mouse, capture if capture is not mouse else None):
            if session is not None:
                try:
                    session.close()
                except Exception:
                    normal_stop = False
                    log.exception('Rafting connection cleanup failed')
                    publish({'status': '连接释放失败，请检查模拟器'})
        publish({'rounds': engine.completed, 'used': engine.used, 'normalStop': normal_stop})
