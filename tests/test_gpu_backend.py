import unittest
from unittest.mock import patch, MagicMock
from PySide6.QtCore import QCoreApplication
from fishing.gpu_app import Backend
from fishing.engine import Settings

class GpuBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QCoreApplication.instance() or QCoreApplication([])
    def setUp(self):
        self.backend=Backend(discover=False,hotkeys=False)
        self.backend.timer.stop()
        self.sound=patch('winsound.MessageBeep');self.sound_mock=self.sound.start();self.addCleanup(self.sound.stop)
        self.save=patch.object(self.backend,'persist');self.save.start()
    def tearDown(self):self.save.stop()
    def test_bait_display_reports_actual_luck_and_finite_wait(self):
        b=self.backend
        b.update(running=True,auto_bait=True,baitDeadline=115,baitPhase=None,
                 rodLevel=1,luckCurrent=4,luckTarget=5,baitStatus='等待补饵 · 恢复满额则取消')
        with patch('fishing.gpu_app.time.monotonic',return_value=100):
            b.refresh_bait_display()
        self.assertIn('15 秒',b.state['baitDisplay'])
        self.assertEqual(b.state['luckText'],'当前最高幸运值 4 / 5 · 待补充')
        b.update(luckCurrent=5,baitDeadline=None,baitStatus='已满')
        b.refresh_bait_display();self.assertTrue(b.state['luckFull'])
        b.update(luckCurrent=None);b.refresh_bait_display()
        self.assertFalse(b.state['luckFull']);self.assertIn('—',b.state['luckText'])

    def test_poll_keeps_last_valid_luck_during_waiting(self):
        b=self.backend;b.update(luckCurrent=4,luckTarget=6)
        b.events.put({'luckCurrent':None,'luckTarget':6});b.poll()
        self.assertEqual(b.state['luckCurrent'],4)
        b.events.put({'luckCurrent':5,'luckTarget':6});b.poll()
        self.assertEqual(b.state['luckCurrent'],5)

    def test_only_normal_auto_stop_requests_shutdown_once(self):
        b=self.backend;b.update(shutdown_on_stop=True,shutdown_force=False,normalStop=True)
        with patch('fishing.shutdown.request_shutdown') as call:
            b.handle_stopped();b.handle_stopped()
            call.assert_not_called()
            self.assertTrue(b.state['shutdownPending'])
            with patch('fishing.gpu_app.time.monotonic',return_value=b.shutdown_deadline):b.tick_shutdown()
            b.tick_shutdown()
            call.assert_called_once_with(False)
        for normal,manual,closing in ((False,False,False),(True,True,False),(True,False,True)):
            b.update(normalStop=normal,closing=closing);b.manual_stop=manual
            with patch('fishing.shutdown.request_shutdown') as call:
                b.handle_stopped();call.assert_not_called()

    def test_shutdown_force_is_explicit_and_failure_reported(self):
        b=self.backend;b.update(shutdown_on_stop=True,shutdown_force=True,normalStop=True)
        with patch('fishing.shutdown.request_shutdown',side_effect=OSError('denied')) as call:
            b.handle_stopped()
            with patch('fishing.gpu_app.time.monotonic',return_value=b.shutdown_deadline):b.tick_shutdown()
            call.assert_called_once_with(True)
        self.assertIn('失败',b.state['shutdownStatus']);self.assertFalse(b.state['shutdownPending'])

    def test_mode_change_queues_safe_boundary_and_manual_stop_cancels(self):
        b=self.backend;b.update(running=True,mode='mumu_sdk')
        b.setMode(1)
        self.assertEqual(b.state['mode'],'mumu_sdk')
        self.assertEqual(b.session_updates.get_nowait(),{'_reconnect':True})
        b.stop();self.assertIsNone(b.pending_change)

    def test_resize_does_not_rediscover_or_reset_session(self):
        b=self.backend;b.session_settings=Settings(desired_multiplier=20)
        b.update(running=True,desired_multiplier=20,catchCount=7,rodsUsed=14)
        with patch.object(b,'refresh') as refresh:
            b.resizeTo(.6825);b.finishResize()
            refresh.assert_not_called()
        self.assertEqual(b.state['ui_scale'],.6825)
        self.assertEqual(b.session_settings.ui_scale,.6825)
        self.assertEqual((b.state['catchCount'],b.state['rodsUsed']),(7,14))
    def test_running_multiplier_and_budget_queue_updates(self):
        b=self.backend;b.update(running=True,rod_budget=500)
        b.setValue('desired_multiplier',3);b.setValue('rod_budget','200')
        self.assertEqual(b.session_updates.get_nowait(),3)
        self.assertEqual(b.state['rod_budget'],200)
        self.assertEqual(b.session_updates.get_nowait(),{'rod_budget':200})
    def test_coalesced_messages_preserve_counts(self):
        b=self.backend
        b.events.put('准备钓鱼 | 已完成 12 次 | 本次用竿 24/500 根')
        b.events.put('已停止');b.poll()
        self.assertEqual((b.state['catchCount'],b.state['rodsUsed']),(12,24))
        self.assertEqual(b.state['status'],'已停止')
    def test_settings_validate_budgets_and_all_modes(self):
        b=self.backend
        for mode in ('mumu_sdk','foreground','maatouch'):
            b.update(mode=mode,rod_budget='123',bait_limit='0',crop_top='0',crop_bottom='0')
            settings=b.validated_settings()
            self.assertEqual((settings.mode,settings.rod_budget,settings.bait_limit),(mode,123,0))
        b.update(rod_budget='-1')
        with self.assertRaises(ValueError):b.validated_settings()
    def test_manual_adb_address_survives_async_refresh(self):
        b=self.backend;b.update(mode='maatouch',deviceIndex=-1,deviceText='127.0.0.1:5555')
        b._devices_ready(b.generation,[], '')
        self.assertEqual(b.state['deviceText'],'127.0.0.1:5555')
    def test_close_waits_for_worker_and_cancels(self):
        b=self.backend;b.worker=type('Worker',(),{'is_alive':lambda self:True})()
        b.closeRequested()
        self.assertTrue(b.cancel.is_set());self.assertFalse(b.state['canClose'])
        b.worker=None;b.poll();self.assertTrue(b.state['canClose'])

    def test_shutdown_has_full_fifteen_seconds_and_cancel_is_final(self):
        b=self.backend;b.update(shutdown_on_stop=True,normalStop=True)
        with patch('fishing.shutdown.request_shutdown') as call:
            with patch('fishing.gpu_app.time.monotonic',return_value=100):b.handle_stopped()
            self.assertEqual(b.shutdown_deadline,115)
            with patch('fishing.gpu_app.time.monotonic',return_value=114.9):b.tick_shutdown()
            self.assertEqual(b.state['shutdownStatus'],'1 秒后关机');call.assert_not_called()
            b.cancelShutdown()
            with patch('fishing.gpu_app.time.monotonic',return_value=116):b.tick_shutdown();b.handle_stopped()
            call.assert_not_called();self.assertFalse(b.state['shutdownPending'])

    def test_stop_close_and_disable_cancel_countdown(self):
        for cancel in (lambda b:b.stop(),lambda b:b.closeRequested(),lambda b:b.setValue('shutdown_on_stop',False)):
            b=Backend(discover=False,hotkeys=False);b.timer.stop()
            b.update(shutdown_on_stop=True,normalStop=True)
            with patch.object(b,'persist'),patch('fishing.shutdown.request_shutdown') as call:
                b.handle_stopped();cancel(b);b.tick_shutdown()
                call.assert_not_called();self.assertFalse(b.state['shutdownPending'])

    def test_expiry_and_auto_bait_mutually_exclusive_live(self):
        b=self.backend;b.update(running=True,auto_bait=True)
        b.setValue('stop_when_buffs_end',True)
        self.assertTrue(b.state['stop_when_buffs_end']);self.assertFalse(b.state['auto_bait'])
        self.assertEqual(b.session_updates.get_nowait(),{'stop_when_buffs_end':True,'auto_bait':False})
        b.setValue('auto_bait',True)
        self.assertFalse(b.state['stop_when_buffs_end']);self.assertTrue(b.state['auto_bait'])

    def test_shutdown_alert_once_and_topmost_restored_on_cancel(self):
        from PySide6.QtCore import Qt
        b=self.backend;b.window=MagicMock();b.window.flags.return_value=Qt.Window
        b.update(shutdown_on_stop=True,normalStop=True)
        b.handle_stopped();b.handle_stopped()
        self.sound_mock.assert_called_once()
        b.window.showNormal.assert_called_once();b.window.raise_.assert_called_once()
        b.window.requestActivate.assert_called_once()
        b.window.setFlag.assert_called_with(Qt.WindowStaysOnTopHint,True)
        b.cancelShutdown()
        b.window.setFlag.assert_called_with(Qt.WindowStaysOnTopHint,False)

    def test_sound_failure_does_not_cancel_countdown(self):
        b=self.backend;self.sound_mock.side_effect=RuntimeError('no audio')
        b.update(shutdown_on_stop=True,normalStop=True);b.handle_stopped()
        self.assertTrue(b.state['shutdownPending']);self.assertIsNotNone(b.shutdown_deadline)

    def test_shutdown_opt_in_is_not_restored_or_saved(self):
        from pathlib import Path
        import json
        with patch.object(Path,'read_text',return_value='{"shutdown_on_stop":true,"rod_budget":123}'):
            b=Backend(discover=False,hotkeys=False);b.timer.stop()
        self.assertFalse(b.state['shutdown_on_stop']);self.assertEqual(b.state['rod_budget'],123)
        b.update(shutdown_on_stop=True)
        with patch.object(Path,'write_text') as write:b.persist()
        self.assertFalse(json.loads(write.call_args.args[0])['shutdown_on_stop'])
        self.assertTrue(b.state['shutdown_on_stop'])

    def test_real_rod_pipeline_reaches_luck_display_before_cast(self):
        import cv2
        from fishing.engine import Engine
        from fishing.vision import Vision
        from fishing.paths import ASSETS
        for name,level,luck in [('ready100',1,1),('multiplier-max',2,2),('gold-ready-real',3,3),('gold-ready-sdk-real',3,4)]:
            v=Vision();g=v.normalize(cv2.imread(str(ASSETS/'fixtures'/f'{name}.png')))
            self.assertEqual(v.read_rod_level(g),level,name)
            e=Engine(Settings(desired_multiplier=1))
            for t in (0,.4,.8):
                o=v.observe(cv2.imread(str(ASSETS/'fixtures'/f'{name}.png')))
                o.rod_level=v.read_rod_level(g);o.luck=v.read_luck(g);o.bait_sample_at=t;o.multiplier=1
                e.step(o,t)
            self.backend.events.put(e.bait.snapshot());self.backend.poll()
            self.assertEqual(self.backend.state['rodLevel'],level,name)
            self.assertEqual(self.backend.state['luckCurrent'],luck,name)
            self.assertEqual(self.backend.state['luckTarget'],level+4,name)
            self.assertIn(f'{luck} / {level+4}',self.backend.state['luckText'],name)
    def test_inconsistent_luck_is_not_displayed_as_full(self):
        b=self.backend;b.update(rodLevel=1,luckCurrent=7,luckTarget=5)
        b.refresh_bait_display()
        self.assertFalse(b.state['luckFull']);self.assertIn('待读数确认',b.state['luckText'])
    def test_unknown_rod_still_displays_clover_reading(self):
        b=self.backend;b.update(rodLevel=None,luckCurrent=4,luckTarget=None)
        b.refresh_bait_display()
        self.assertIn('4 / —',b.state['luckText']);self.assertIn('待识别鱼竿',b.state['luckText'])

    def test_protection_runtime_update_does_not_toggle_other_settings(self):
        b=self.backend
        b.update(running=True,auto_bait=True,stop_on_bait_end=False,full_bait_protection=False)
        b.setValue('full_bait_protection',True)
        self.assertTrue(b.state['auto_bait']);self.assertFalse(b.state['stop_on_bait_end'])
        self.assertEqual(b.session_updates.get_nowait(),{'full_bait_protection':True})

