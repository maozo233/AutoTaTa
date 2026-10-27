import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import numpy as np
from fishing.adb_session import AdbSession,discover_mumu_device
from fishing.engine import Settings


def device(index=0,mumu=True):
    return SimpleNamespace(adb_path='mumu-adb.exe',address=f'127.0.0.1:{16384+index}',config={'extras':{'mumu':{'enable':mumu,'index':index}}})

class AdbSessionTests(unittest.TestCase):
    def session(self):
        with patch('fishing.adb_session.process_id',return_value=456):return AdbSession(123,threading.Event())

    def test_only_mumu_device_selected(self):
        expected=device()
        with patch('fishing.adb_session.initialize'),patch('maa.toolkit.Toolkit.find_adb_devices',return_value=[device(1,False),expected]):
            self.assertIs(discover_mumu_device(),expected)

    def test_multiple_instances_refused(self):
        with patch('fishing.adb_session.initialize'),patch('maa.toolkit.Toolkit.find_adb_devices',return_value=[device(),device(1)]):
            with self.assertRaisesRegex(RuntimeError,'多个'):discover_mumu_device()

    def test_default_is_sdk(self):self.assertEqual(Settings().mode,'mumu_sdk')

    def test_connect_forces_device_input_and_extras_capture(self):
        from maa.define import MaaAdbInputMethodEnum as I,MaaAdbScreencapMethodEnum as S
        session=self.session();controller=MagicMock();controller.resolution=(900,1600)
        with patch.object(session,'validate',return_value=True),patch('fishing.display_probe.inspect_fishing_displays',return_value=({'bound':True},(2,900,1600))),patch('fishing.maatouch_display.prepare_maatouch_display',return_value=({'patched':True},(2,900,1600))),patch('fishing.adb_session.discover_mumu_device',return_value=device()),patch('fishing.adb_session.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=b'connected to 127.0.0.1:16384')),patch('maa.controller.AdbController',return_value=controller) as factory:
            session.start()
        self.assertEqual(factory.call_args.kwargs['input_methods'],I.Maatouch)
        self.assertEqual(factory.call_args.kwargs['config'],{'patched':True})
        self.assertEqual(factory.call_args.kwargs['screencap_methods'],S.EmulatorExtras)
        self.assertEqual(session.size,(900,1600))

    def test_sdk_forces_matching_emulator_input_without_maatouch_fallback(self):
        from maa.define import MaaAdbInputMethodEnum as I,MaaAdbScreencapMethodEnum as S
        session=self.session();session.mode='mumu_sdk';session.input_name='MuMu SDK'
        controller=MagicMock();controller.resolution=(900,1600)
        with patch.object(session,'validate',return_value=True),patch('fishing.display_probe.inspect_fishing_displays',return_value=({'bound':True},(2,900,1600))),patch('fishing.maatouch_display.prepare_maatouch_display',return_value=({'patched':True},(2,900,1600))),patch('fishing.adb_session.discover_mumu_device',return_value=device()),patch('fishing.adb_session.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=b'connected to 127.0.0.1:16384')),patch('maa.controller.AdbController',return_value=controller) as factory:
            session.start()
        self.assertEqual(factory.call_args.kwargs['input_methods'],I.EmulatorExtras)
        self.assertEqual(factory.call_args.kwargs['screencap_methods'],S.EmulatorExtras)
        self.assertEqual(session.size,(900,1600))

    def test_click_uses_device_coordinates_and_rejects_overflow(self):
        session=self.session();session.controller=MagicMock();session.size=(900,1600)
        with patch.object(session,'validate',return_value=True):
            session.click((450,1200))
            session.controller.post_click.assert_called_once_with(450,1200)
            with self.assertRaises(RuntimeError):session.click((901,1200))

    def test_screenshot_resolution_change_stops(self):
        session=self.session();session.controller=MagicMock();session.size=(900,1600);session.controller.cached_image=np.zeros((900,1600,3),np.uint8)
        with patch.object(session,'validate',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'分辨率'):session.read()

    def test_cancel_prevents_input(self):
        session=self.session();session.cancel.set();session.controller=MagicMock();session.click((450,1200));session.controller.post_click.assert_not_called()

    def test_close_is_idempotent(self):
        session=self.session();session.controller=MagicMock()
        with patch('fishing.adb_session.wait_job'):
            session.close();session.close()
        session.controller.post_inactive.assert_called_once()
