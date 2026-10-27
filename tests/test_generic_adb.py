import unittest,threading,cv2
from unittest.mock import patch,MagicMock
from types import SimpleNamespace
from fishing.generic_adb import GenericAdbSession,decode_adb_png,adb_version_supported
from fishing.engine import Settings
from fishing.paths import ASSETS

class GenericTests(unittest.TestCase):
    def test_virtual_display_two_uses_only_adb_encode_and_maatouch(self):
        frame=cv2.imread(str(ASSETS/'fixtures/ready.png'))
        settings=Settings(mode='maatouch',adb_path='adb.exe',adb_address='serial')
        session=GenericAdbSession(settings,threading.Event())
        controller=MagicMock();controller.resolution=(frame.shape[1],frame.shape[0])
        with patch('fishing.generic_adb.initialize'),patch('fishing.generic_adb.adb_version_supported',return_value=True),patch.object(session,'command',return_value=b'Display: mDisplayId=2'),patch.object(session,'snapshot',return_value=frame),patch('fishing.vision.Vision.read_multiplier',return_value=2),patch('fishing.display_probe.DisplayProbe',side_effect=AssertionError('Emulator SDK forbidden')),patch('fishing.adb_stream.AdbFrameStream'),patch('maa.controller.AdbController',return_value=controller) as factory:
            session.start()
        from maa.define import MaaAdbInputMethodEnum as I,MaaAdbScreencapMethodEnum as S
        args=factory.call_args.kwargs
        self.assertEqual(args['input_methods'],I.Maatouch);self.assertEqual(args['screencap_methods'],S.Encode)
        self.assertNotIn('extras',args['config'])
        self.assertTrue(args['config']['command']['InvokeApp'][-1].endswith('{PACKAGE_NAME} 2'))
        self.assertEqual(session.display_binding,(2,frame.shape[1],frame.shape[0]))
    def test_old_adb_version_is_rejected(self):
        with patch('fishing.generic_adb.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=b'Android Debug Bridge version 1.0.32')):
            self.assertFalse(adb_version_supported('adb.exe'))
    def test_png_newline_conversion_is_repaired_without_altering_normal_png(self):
        frame=cv2.imread(str(ASSETS/'fixtures/ready.png'));ok,encoded=cv2.imencode('.png',frame);self.assertTrue(ok)
        original=encoded.tobytes();converted=original.replace(b'\n',b'\r\n')
        self.assertTrue((decode_adb_png(original)==frame).all())
        self.assertTrue((decode_adb_png(converted)==frame).all())

    def test_fast_capture_jpeg_preserves_fishing_states(self):
        from fishing.vision import Vision
        ready=cv2.imread(str(ASSETS/'fixtures/ready.png'))
        original_vision=Vision();original_vision.observe(ready)
        jpeg_vision=Vision();_,ready_jpeg=cv2.imencode('.jpg',ready,[cv2.IMWRITE_JPEG_QUALITY,95]);jpeg_vision.observe(cv2.imdecode(ready_jpeg,cv2.IMREAD_COLOR))
        for name in ('ready','waiting','hook','fight-inside','fight-outside','result'):
            frame=cv2.imread(str(ASSETS/'fixtures'/f'{name}.png'))
            before=original_vision.observe(frame)
            ok,encoded=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,95]);self.assertTrue(ok)
            after=jpeg_vision.observe(cv2.imdecode(encoded,cv2.IMREAD_COLOR))
            self.assertEqual(after.state,before.state,name)
            self.assertEqual(after.in_yellow,before.in_yellow,name)
    def test_controller_released_even_when_stream_cleanup_fails(self):
        session=GenericAdbSession(Settings(),threading.Event())
        session.stream=MagicMock();session.stream.close.side_effect=OSError('stream failed')
        session.controller=MagicMock()
        with patch('fishing.adb_session.wait_job') as wait:
            with self.assertRaises(OSError):session.close()
            wait.assert_called_once()
        self.assertIsNone(session.stream)
        session.controller.post_inactive.assert_called_once()
