import threading
import unittest
from unittest.mock import MagicMock, patch
from fishing.maa_input import create_controller
from fishing.windows import Mouse
from fishing.gpu_app import Backend
from PySide6.QtCore import QCoreApplication
from fishing.hotkeys import START_KEY, STOP_KEY

class InputTests(unittest.TestCase):
    def test_background_controller_uses_synthetic_touch(self):
        from maa.define import MaaWin32InputMethodEnum as Input
        with patch('fishing.maa_input.initialize'), patch('maa.controller.Win32Controller') as controller:
            create_controller(123, 'background')
            self.assertEqual(controller.call_args.kwargs['mouse_method'], Input.AnchoredTouch)
            self.assertEqual(controller.call_args.kwargs['keyboard_method'], Input.PostMessage)

    def test_mouse_background_route_selects_touch(self):
        with patch('fishing.windows.process_id', return_value=456), patch('fishing.windows.client_rect', return_value=(0,0,528,979)), patch('fishing.windows.MaaInput') as backend:
            Mouse(123, 'background', threading.Event())
            backend.assert_called_once_with(123, 'background')

    def test_background_emergency_release_clears_synthetic_contact(self):
        mouse=Mouse.__new__(Mouse)
        mouse.mode='background'
        mouse.backend=MagicMock()
        with patch('fishing.windows.user32.PostMessageW') as message:
            mouse.emergency_release((264,805))
            mouse.backend.deactivate.assert_called_once()
            message.assert_not_called()

    @classmethod
    def setUpClass(cls):cls.qt=QCoreApplication.instance() or QCoreApplication([])

    def fake_app(self):
        app=Backend(discover=False,hotkeys=True)
        app.timer.stop()
        app.persist=MagicMock()
        app.start=MagicMock()
        return app

    def test_home_starts_and_pgdown_stops(self):
        app=self.fake_app()
        with patch('fishing.gpu_app.user32.GetAsyncKeyState', side_effect=lambda key:1 if key==0x24 else 0):
            app.poll()
        app.start.assert_called_once()
        self.assertFalse(app.cancel.is_set())
        with patch('fishing.gpu_app.user32.GetAsyncKeyState', side_effect=lambda key:1 if key==0x22 else 0):
            app.poll()
        self.assertTrue(app.cancel.is_set())

    def test_end_is_no_longer_the_stop_key(self):
        app=self.fake_app()
        with patch('fishing.gpu_app.user32.GetAsyncKeyState', side_effect=lambda key:1 if key==0x23 else 0):
            app.poll()
        self.assertFalse(app.cancel.is_set())

    def test_disabled_hotkeys_do_not_poll_or_start(self):
        app=self.fake_app();app.hotkeys=False
        with patch('fishing.gpu_app.user32.GetAsyncKeyState',return_value=1) as read:
            app.poll()
        read.assert_not_called();app.start.assert_not_called()
        self.assertFalse(app.cancel.is_set())

if __name__=='__main__':
    unittest.main()
