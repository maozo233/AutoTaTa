import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from fishing.maa_input import new_input_failure, MaaInput
from fishing.windows import Mouse


class InputFailureTests(unittest.TestCase):
    def mouse(self):
        mouse=Mouse.__new__(Mouse)
        mouse.backend=MagicMock()
        mouse.validate=MagicMock(return_value=True)
        mouse.cancel=threading.Event()
        mouse.mode='background'
        return mouse

    def test_failed_down_does_not_send_up_and_preserves_original(self):
        mouse=self.mouse()
        original=RuntimeError('occluded')
        mouse.backend.down.side_effect=original
        with self.assertRaises(RuntimeError) as raised:mouse.click((10,20))
        self.assertIs(raised.exception,original)
        mouse.backend.up.assert_not_called()
        mouse.backend.deactivate.assert_called_once()

    def test_cleanup_failure_does_not_mask_original(self):
        mouse=self.mouse()
        original=RuntimeError('down failed')
        mouse.backend.down.side_effect=original
        mouse.backend.deactivate.side_effect=RuntimeError('cleanup failed')
        with self.assertLogs('fishing',level='ERROR'):
            with self.assertRaises(RuntimeError) as raised:mouse.click((10,20))
        self.assertIs(raised.exception,original)

    def test_successful_down_still_releases_contact(self):
        mouse=self.mouse()
        mouse.cancel.set()
        mouse.click((10,20))
        mouse.backend.down.assert_called_once_with(10,20)
        mouse.backend.up.assert_called_once()

    def test_diagnostics_ignore_old_and_other_process_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'maa.log'
            old=f'[ERR][Px{os.getpid()}] still occluded after being raised\n'
            path.write_text(old,encoding='utf-8');offset=path.stat().st_size
            with path.open('a',encoding='utf-8') as stream:stream.write('[ERR][Px0] the target point is outside the desktop\n')
            with patch('fishing.maa_input.maa_log_path',return_value=path):
                self.assertEqual(new_input_failure(offset),'')
            with path.open('a',encoding='utf-8') as stream:stream.write(f'[ERR][Px{os.getpid()}] still occluded after being raised\n')
            with patch('fishing.maa_input.maa_log_path',return_value=path):
                self.assertIn('遮挡',new_input_failure(offset))

    def test_offscreen_has_distinct_hint(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'maa.log'
            path.write_text(f'[ERR][Px{os.getpid()}] the target point is outside the desktop',encoding='utf-8')
            with patch('fishing.maa_input.maa_log_path',return_value=path):
                self.assertIn('超出桌面',new_input_failure(0))

    def test_down_surfaces_current_reason(self):
        backend=MaaInput.__new__(MaaInput)
        backend.controller=MagicMock();backend.log=MagicMock();backend.hwnd=1;backend.mode='background'
        with patch('fishing.anchor_guard.check_anchor'),patch('fishing.maa_input.log_offset',return_value=100),patch('fishing.maa_input.wait_job',side_effect=RuntimeError('generic')),patch('fishing.maa_input.new_input_failure',return_value='still covered'):
            with self.assertRaisesRegex(RuntimeError,'still covered'):backend.down(10,20)
