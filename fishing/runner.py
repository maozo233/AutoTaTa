import logging
import queue
import time
import cv2
from .engine import Engine
from .vision import Vision
from .windows import WindowCapture, Mouse, FocusLost, user32
from .paths import ROOT
from .hotkeys import STOP_KEY, STOP_LABEL

def apply_multiplier_updates(engine, updates):
    if updates is None:
        return False
    changed = False
    pending = getattr(engine, 'runtime_pending', {})
    while True:
        try:
            update = updates.get_nowait()
        except queue.Empty:
            break
        if isinstance(update, dict):
            pending.update(update)
        else:
            pending['desired_multiplier'] = update
    if '_reconnect' in pending:
        engine.reconnect_requested = pending.pop('_reconnect')
    for key in list(pending):
        if key in ('crop_top','crop_bottom'):
            continue  # Apply together on a fresh ready frame, never during a fight.
        value = pending.pop(key)
        if key == 'desired_multiplier':
            changed = engine.update_desired_multiplier(value) or changed
        elif key in ('auto_bait','full_bait_protection','stop_on_bait_end','stop_when_buffs_end','bait_limit','rod_budget'):
            setattr(engine.settings, key, value)
    engine.runtime_pending = pending
    return changed


def run(hwnd, settings, cancel, publish, updates=None, bait_update=None, initial_counts=None):
    capture = mouse = None
    stop_reason = None
    engine = Engine(settings)
    if initial_counts:
        engine.catch_count, engine.rods_used, engine.bait_used = initial_counts
    last_bait_snapshot = None
    def report_bait():
        nonlocal last_bait_snapshot
        snapshot = engine.bait.snapshot()
        if bait_update is not None and snapshot != last_bait_snapshot:
            bait_update(snapshot)
            last_bait_snapshot = snapshot
    report_bait()
    vision = Vision(settings.crop_top, settings.crop_bottom)
    log = logging.getLogger('fishing')
    try:
        publish(f'正在连接游戏设备；{STOP_LABEL} 可停止。')
        if settings.mode == 'maatouch':
            from .generic_adb import GenericAdbSession
            capture = mouse = GenericAdbSession(settings, cancel)
            capture.start()
        elif settings.mode == 'mumu_sdk':
            from .adb_session import AdbSession
            capture = mouse = AdbSession(hwnd, cancel, mode=settings.mode)
            capture.start()
        else:
            capture = WindowCapture(hwnd)
            capture.start()
            mouse = Mouse(hwnd, settings.mode, cancel)
        started = time.monotonic()
        last_seq = -1
        last_ocr = -100.
        last_rods_ocr = -100.
        remaining_rods = None
        last_bait_ocr = -100.
        bait_reading = None
        multiplier = None
        last_status = ''
        last_perf = -100.
        fast_phase = False
        fallback_reported = False
        deferred_ocr_state = None
        upgrade_hint = False
        last_stale_report = -100.
        while not cancel.wait(.001 if fast_phase else .012):
            if user32.GetAsyncKeyState(STOP_KEY) & 0x8000:
                break
            if apply_multiplier_updates(engine, updates):
                last_ocr = -100.
                publish(f'期望倍率已更新为 x{settings.desired_multiplier}，下一次抛竿前应用。')
            now = time.monotonic()
            capture_start = time.monotonic()
            sample = capture.read()
            capture_ms = (time.monotonic()-capture_start)*1000
            if capture_ms>500:
                log.warning('Slow capture mode=%s elapsed_ms=%.1f foreground=%s',settings.mode,capture_ms,user32.GetForegroundWindow())
            if settings.mode=='mumu_sdk' and getattr(capture,'fallback_session',None) is not None and not fallback_reported:
                fallback_reported=True
                publish(f'{capture.fallback_reason}，本次已切换Android截图＋MaaTouch；重新开始可恢复MuMuSDK。')
            if sample is None:
                if now-started > 6:
                    raise RuntimeError('未收到游戏画面，请恢复 MuMu 窗口。')
                continue
            frame, captured_at, seq, size = sample
            if size != mouse.size:
                raise RuntimeError('窗口尺寸已变化，请重新开始。')
            if now-captured_at > 1.5:
                raise RuntimeError('画面已停止更新，已停止点击。')
            if seq == last_seq:
                continue
            last_seq = seq
            if settings.mode == 'foreground' and user32.GetForegroundWindow() != hwnd:
                publish('游戏不在前台，已暂停；切回游戏后继续。')
                # Invalidate cached decisions and cooldowns while focus is absent.
                engine.ready_since = None
                last_ocr = -100.
                continue
            vision_start = time.monotonic()
            obs = vision.observe(frame)
            # After slow OCR, reserve one fresh same-state frame for decisions.
            # Otherwise due OCR can repeat forever before the freshness gate.
            allow_ready_ocr = obs.state != deferred_ocr_state
            deferred_ocr_state = None
            vision_ms = (time.monotonic()-vision_start)*1000
            if obs.state == 'ready' and not engine.bait_phase and not engine.pending_rods:
                if getattr(engine, 'reconnect_requested', False):
                    publish({'reconnectReady': True})
                    break
                pending = getattr(engine, 'runtime_pending', {})
                crop = {k: pending.pop(k) for k in ('crop_top','crop_bottom') if k in pending}
                if crop:
                    for key, value in crop.items(): setattr(settings, key, value)
                    vision = Vision(settings.crop_top, settings.crop_bottom)
                    engine.ready_since = None
                    from .bait import StableReading
                    engine.bait.grade = StableReading();engine.bait.luck = StableReading();engine.bait.stock = StableReading()
                    last_ocr = last_rods_ocr = last_bait_ocr = -100.
                    bait_reading = None
                    continue
            fast_phase = obs.state in ("hook", "fight", "purple_wait")
            if obs.state in ('ready', 'bait_menu'):
                if obs.state == 'ready':
                    if allow_ready_ocr and now-last_rods_ocr >= .35:
                        remaining_rods = vision.read_remaining_rods(vision.normalize(frame))
                        last_rods_ocr = time.monotonic()
                    obs.remaining_rods = remaining_rods
                else:
                    last_rods_ocr = -100.
                if allow_ready_ocr and obs.state == 'ready' and engine.needs_multiplier() and (now-last_ocr >= .35 or obs.multiplier_max):
                    multiplier = vision.read_multiplier(vision.normalize(frame))
                    last_ocr = time.monotonic()
                obs.multiplier = multiplier
                if obs.state=='ready' and multiplier is None:
                    if allow_ready_ocr:
                        upgrade_hint=vision.read_rod_upgrade_hint(vision.normalize(frame))
                    obs.rod_upgrade_hint=upgrade_hint
                    if obs.rod_upgrade_hint:
                        obs.dismiss_point=vision.point(270,vision.normalize(frame).shape[0]-330)

            if obs.state in ('ready', 'bait_menu'):
                game = vision.normalize(frame)
                if allow_ready_ocr and now-last_bait_ocr >= .4:
                    level = vision.read_rod_level(game)
                    luck = vision.read_luck(game)
                    stock = vision.read_bait_stock(game, obs.bait_available) if settings.auto_bait or engine.bait_phase else None
                    capped = vision.read_bait_cap(game) if engine.bait_phase in ('verifying', 'closing') else False
                    last_bait_ocr = time.monotonic()
                    bait_reading = (level, luck, stock, capped, last_bait_ocr)
                if bait_reading:
                    obs.rod_level, obs.luck, obs.bait_stock, obs.bait_capped, obs.bait_sample_at = bait_reading
            else:
                bait_reading = None
                last_bait_ocr = -100.
                if engine.bait_phase:
                    obs.bait_motion = vision.bait_animation(vision.normalize(frame))
            if obs.state not in ('ready','bait_menu'):
                last_rods_ocr = -100.
                remaining_rods = None
            # OCR can take longer on the first frame while the models load.
            frame_age = time.monotonic()-captured_at
            if frame_age > .8:
                if obs.state in ('ready', 'bait_menu'):
                    deferred_ocr_state = obs.state
                if time.monotonic()-last_stale_report >= 2:
                    last_stale_report = time.monotonic()
                    log.warning('Decision frame stale state=%s age_ms=%.1f defer_ocr=%s foreground=%s', obs.state, frame_age*1000, deferred_ocr_state, user32.GetForegroundWindow())
                    if obs.state == 'ready':
                        publish('已回到待钓界面，数字识别较慢；正在获取新画面确认。')
                continue
            # Also consume changes made while OCR was processing this frame.
            if apply_multiplier_updates(engine, updates):
                last_ocr = -100.
                publish(f'期望倍率已更新为 x{settings.desired_multiplier}，下一次抛竿前应用。')
            if obs.state == 'ready' and not engine.bait_phase and not engine.pending_rods and (getattr(engine,'reconnect_requested',False) or getattr(engine,'runtime_pending',{})):
                continue
            action = engine.step(obs, time.monotonic())
            if action.kind == 'stop':
                if action.purpose == 'auto_stop':
                    stop_reason=action.message
                    log.info('Normal automatic stop: %s',stop_reason)
                    publish({'normalStop':True})
                    publish(action.message)
                    break
                raise RuntimeError(action.message)
            input_start = time.monotonic()
            if action.kind == 'click':
                try:
                    log.info('Action submitted state=%s purpose=%s point=%s frame_age_ms=%.1f', obs.state, action.purpose or action.message, action.point, (time.monotonic()-captured_at)*1000)
                    if action.purpose=='cast_fallback':mouse.fallback_click(action.point)
                    else:mouse.click(action.point)
                    if not cancel.is_set():
                        engine.acknowledge(action, time.monotonic())
                        report_bait()
                except FocusLost as exc:
                    publish(str(exc))
                    engine.ready_since = None
                    if action.purpose.startswith('bait_'):
                        raise RuntimeError('打窝操作被中断，结果未确认；已停止，不会自动重复提交。') from exc
            input_ms = (time.monotonic()-input_start)*1000
            report_bait()
            status = action.message or {'ready':'准备钓鱼', 'waiting':'等待咬杆', 'hook':'咬杆提示', 'fight':'控鱼', 'purple_wait':'等待控鱼画面', 'result':'结算', 'unknown':'等待钓鱼界面'}.get(obs.state, obs.state)
            if status != last_status:
                bait_status = f'｜本机用饵 {engine.bait_used}/{settings.bait_limit or "不限"}' if settings.auto_bait else ''
                if engine.bait_limit_reached() and settings.auto_bait:
                    bait_status += '（已达上限）'
                publish(f'{status}｜已完成 {engine.catch_count} 次｜本次用竿 {engine.rods_used}/{settings.rod_budget or "不限"} 根{bait_status}')
                last_status = status
                if obs.state in ('ready', 'bait_menu') or engine.bait_phase:
                    log.info('bait level=%s luck=%s target=%s stock=%s used=%s phase=%s motion=%s capped=%s',obs.rod_level,obs.luck,engine.bait.target,obs.bait_stock,engine.bait_used,engine.bait_phase,obs.bait_motion,obs.bait_capped)
                log.info('state=%s action=%s multiplier=%s desired=%s multiplier_max=%s remaining_rods=%s timer=%s yellow=%s float=%s', obs.state, action.kind, obs.multiplier, settings.desired_multiplier, obs.multiplier_max, obs.remaining_rods, obs.timer, obs.yellow, obs.float_x)
            if fast_phase and (action.kind == 'click' or time.monotonic()-last_perf >= .2):
                last_perf = time.monotonic()
                log.info('fight-perf round=%s attempt=%s early=%s state=%s action=%s capture_ms=%.2f vision_ms=%.2f frame_age_ms=%.2f input_ms=%.2f yellow=%s float=%s',
                         engine.fight_round,engine.fight_clicks,engine.fight_early,obs.state,action.kind,capture_ms,vision_ms,(input_start-captured_at)*1000,
                         input_ms,obs.yellow,obs.float_x)
        publish(f'{stop_reason or "已停止。"}｜本次用竿 {engine.rods_used}/{settings.rod_budget or "不限"} 根｜已完成 {engine.catch_count} 次')
    except Exception as exc:
        publish({'normalStop':False,'reconnectReady':False})
        log.exception('Session stopped')
        try:
            sample = (capture.latest if settings.mode in ('maatouch', 'mumu_sdk') else capture.read()) if capture else None
            if sample:
                folder = ROOT / 'logs'
                folder.mkdir(exist_ok=True)
                cv2.imwrite(str(folder / 'last-stop.png'), sample[0])
        except Exception:
            pass
        publish(f'已停止：{exc}｜本次用竿 {engine.rods_used}/{settings.rod_budget or "不限"} 根｜已完成 {engine.catch_count} 次')
    finally:
        report_bait()
        cancel.set()
        if mouse:
            try:
                mouse.close()
            except Exception:
                publish({'normalStop':False,'reconnectReady':False})
                publish('输入连接释放失败，取消自动关机与重连。')
                log.exception('Input cleanup failed')
        if capture and capture is not mouse:
            try:
                capture.close()
            except Exception:
                publish({'normalStop':False,'reconnectReady':False})
                publish('截图连接释放失败，取消自动关机与重连。')
                log.exception('Capture cleanup failed')
