import threading,unittest
from types import SimpleNamespace
from unittest.mock import patch,MagicMock
import numpy as np
from fishing.adb_session import AdbSession
from fishing.display_probe import SdkCaptureUnavailable

class FailureFallbackTests(unittest.TestCase):
    def session(self):
        s=AdbSession(1,threading.Event(),mode='mumu_sdk')
        s.device=SimpleNamespace(adb_path='adb.exe',address='127.0.0.1:16384')
        s.display_binding=(2,900,1600);s.size=(900,1600)
        s.controller=MagicMock();s.controller.cached_image=np.zeros((1600,900,3),np.uint8)
        s.validate=lambda:not s.cancel.is_set()
        return s
    def replacement(self):
        r=MagicMock();r.size=(900,1600);r.display_binding=(2,900,1600)
        r.read.return_value=(np.zeros((1600,900,3),np.uint8),1,1,r.size)
        return r
    def test_fullscreen_does_not_switch_capture_or_click(self):
        s=self.session()
        with patch('fishing.windows.fullscreen_covering',return_value=True),patch('fishing.generic_adb.GenericAdbSession') as factory:
            s.read();s.click((450,1305));s.read()
        factory.assert_not_called();self.assertIsNone(s.fallback_session)
        self.assertEqual(s.controller.post_screencap.call_count,2)
        s.controller.post_click.assert_called_once_with(450,1305)
    def test_failed_capture_switches_once_and_keeps_sequence_increasing(self):
        s=self.session();s.sequence=20;r=self.replacement()
        with patch.object(s,'wait',side_effect=RuntimeError('capture failed')),patch('fishing.generic_adb.GenericAdbSession',return_value=r):
            self.assertEqual(s.read()[2],21);s.click((450,1305));self.assertEqual(s.read()[2],22)
        r.start_verified.assert_called_once_with((2,900,1600));r.click.assert_called_once_with((450,1305))
        s.close();r.close.assert_called_once()
    def test_empty_image_triggers_fallback(self):
        s=self.session();s.controller.cached_image=None;r=self.replacement()
        with patch('fishing.generic_adb.GenericAdbSession',return_value=r):s.read()
        self.assertIs(s.fallback_session,r)
    def test_size_mismatch_does_not_switch(self):
        s=self.session();s.controller.cached_image=np.zeros((900,1600,3),np.uint8)
        with patch('fishing.generic_adb.GenericAdbSession') as factory:
            with self.assertRaisesRegex(RuntimeError,'分辨率'):s.read()
        factory.assert_not_called()
    def test_fallback_size_mismatch_is_closed_without_click(self):
        s=self.session();r=self.replacement();r.size=(1600,900)
        with patch.object(s,'wait',side_effect=RuntimeError('capture failed')),patch('fishing.generic_adb.GenericAdbSession',return_value=r):
            with self.assertRaisesRegex(RuntimeError,'尺寸'):s.read()
        r.close.assert_called_once();r.click.assert_not_called();self.assertIsNone(s.fallback_session)
    def test_cancel_during_failed_capture_does_not_connect_adb(self):
        s=self.session()
        def failed(*args):s.cancel.set();raise RuntimeError('stopped')
        with patch.object(s,'wait',side_effect=failed),patch('fishing.generic_adb.GenericAdbSession') as factory:
            with self.assertRaisesRegex(RuntimeError,'stopped'):s.read()
        factory.assert_not_called()
    def test_startup_probe_failure_uses_independent_display_validation(self):
        s=self.session();s.display_binding=None;s.size=None;r=self.replacement()
        with patch('fishing.adb_session.discover_mumu_device',return_value=s.device),patch('fishing.adb_session.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=b'connected to a')),patch('fishing.display_probe.inspect_fishing_displays',side_effect=SdkCaptureUnavailable('no image')),patch('fishing.generic_adb.GenericAdbSession',return_value=r):s.start()
        r.start.assert_called_once_with(allow_active=True)
        r.start_verified.assert_not_called()
    def test_ambiguous_display_error_must_not_trigger_fallback(self):
        s=self.session()
        with patch('fishing.adb_session.discover_mumu_device',return_value=s.device),patch('fishing.adb_session.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=b'connected to a')),patch('fishing.display_probe.inspect_fishing_displays',side_effect=RuntimeError('multiple matches')),patch('fishing.generic_adb.GenericAdbSession') as factory:
            with self.assertRaisesRegex(RuntimeError,'multiple'):s.start()
        factory.assert_not_called()
    def test_fullscreen_startup_still_initializes_sdk(self):
        s=self.session();c=s.controller;c.resolution=s.size
        with patch('fishing.windows.fullscreen_covering',return_value=True),patch('fishing.adb_session.discover_mumu_device',return_value=s.device),patch('fishing.adb_session.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=b'connected to a')),patch('fishing.display_probe.inspect_fishing_displays',return_value=({},s.display_binding)),patch('maa.controller.AdbController',return_value=c),patch('fishing.generic_adb.GenericAdbSession') as factory:
            s.start()
        factory.assert_not_called();c.post_screencap.assert_called_once()
    def test_first_sdk_screenshot_failure_switches_after_display_validation(self):
        s=self.session();r=self.replacement()
        with patch.object(s,'wait',side_effect=[None,RuntimeError('capture failed')]),patch('fishing.adb_session.discover_mumu_device',return_value=s.device),patch('fishing.adb_session.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=b'connected to a')),patch('fishing.display_probe.inspect_fishing_displays',return_value=({},s.display_binding)),patch('maa.controller.AdbController',return_value=s.controller),patch('fishing.generic_adb.GenericAdbSession',return_value=r):
            s.start()
        r.start_verified.assert_called_once_with((2,900,1600))
    def test_sdk_released_even_when_fallback_cleanup_fails(self):
        s=self.session();r=self.replacement();s.fallback_session=r;r.close.side_effect=OSError('stream cleanup failed')
        with patch('fishing.adb_session.wait_job') as wait:
            with self.assertRaises(OSError):s.close()
            wait.assert_called_once()
        s.controller.post_inactive.assert_called_once();self.assertIsNone(s.fallback_session)
