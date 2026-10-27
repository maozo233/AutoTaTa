import json
from pathlib import Path
import cv2
from .paths import ASSETS
from .vision import Vision

def selftest(destination, verify_maatouch=False):
    report = {}
    vision = Vision()
    for name, state in [('ready','ready'), ('live-ready','ready'), ('waiting','waiting'), ('hook','hook'),
                        ('fight-outside','fight'), ('fight-inside','fight'), ('result','result')]:
        obs = vision.observe(cv2.imread(str(ASSETS/'fixtures'/f'{name}.png')))
        assert obs.state == state, (name, obs)
        if name == 'fight-inside':
            assert obs.in_yellow
        if name == 'fight-outside':
            assert not obs.in_yellow
        report[name] = {'state':obs.state, 'in_yellow':obs.in_yellow}
    for name, expected in [('ready',1), ('ready100',100)]:
        obs = Vision().observe(cv2.imread(str(ASSETS/'fixtures'/f'{name}.png')), True, True)
        assert obs.multiplier == expected, (name, obs)
        assert obs.bait_available
        assert obs.timer == 'absent', 'Multiplier inside the clover must not count as a timer'
        report[f'ocr-{expected}'] = True
    obs = Vision().observe(cv2.imread(str(ASSETS/'fixtures/bait-menu.png')), True, True)
    assert obs.state == 'bait_menu' and obs.timer == 'active' and obs.multiplier == 10
    assert 390 < obs.bait_confirm_point[0] < 465 and 575 < obs.bait_confirm_point[1] < 625
    report['bait-menu-and-real-timer'] = True
    switch_vision = Vision()
    for value in (1,2,3,5,10,20,50,100):
        obs = switch_vision.observe(cv2.imread(str(ASSETS/'fixtures'/f'multiplier-{value}.png')), True)
        assert obs.state == 'ready' and obs.multiplier == value, (value, obs)
    report['all-eight-video-multipliers'] = True
    for name,expected in (('multiplier-max',491),('ready100',1658)):
        counter=Vision();frame=cv2.imread(str(ASSETS/'fixtures'/f'{name}.png'))
        counter.observe(frame)
        assert counter.read_remaining_rods(counter.normalize(frame))==expected
    report['remaining-rods-real-counters']=True
    from .windows import window_details
    report['mumu_windows'] = len(window_details())
    from .maa_input import create_controller
    from .gpu_validation import validate_gpu_ui
    hwnd = validate_gpu_ui(report)
    # Validate packaged DLL loading; sends no game clicks.
    for mode in ('foreground', 'background'):
        controller = create_controller(hwnd, mode)
        assert controller
        report[f'maa-{mode}-loaded'] = True
    if verify_maatouch:
        import threading
        from .generic_adb import GenericAdbSession,discover_adb_entries
        from .engine import Settings
        devices=discover_adb_entries()
        assert devices, 'ADB device must be running for the optional check'
        session=GenericAdbSession(Settings(mode='maatouch',adb_path=devices[0]['adb_path'],adb_address=devices[0]['adb_address']),threading.Event())
        try:
            session.start()
            sample = session.read()
            assert sample and sample[0].shape[1::-1] == session.size
            report['packaged-maatouch-device-capture'] = list(session.size)
            report['packaged-maatouch-no-input-sent'] = True
        finally:
            session.close()
    import tempfile, logging
    from .log_policy import BoundedSessionHandler,LogMaintenance,MAX_LOG_BYTES
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);path=root/'logs/session.log'
        handler=BoundedSessionHandler(path,512)
        try:
            for i in range(80):
                handler.handle(logging.LogRecord('test',20,'',0,'控鱼记录 %s',(i,),None))
        finally:handler.close()
        assert path.stat().st_size<=512 and Path(str(path)+'.1').stat().st_size<=512
        assert '79' in path.read_text(encoding='utf-8')
        native=root/'maa/debug/maafw.log';native.parent.mkdir(parents=True)
        native.write_bytes(b'old record\n'*500000)
        LogMaintenance(root).sweep()
        assert sum(p.stat().st_size for p in root.rglob('*.log*'))<MAX_LOG_BYTES
        report['log-rotation-utf8-and-native-size-budget']=True
    report['passed'] = True
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
