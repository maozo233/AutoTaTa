import threading
import time
import unittest
from unittest.mock import patch, MagicMock
from fishing.engine import Settings, Action
from fishing.vision import Observation
from fishing.runner import run

class StopOutcomeTests(unittest.TestCase):
    def execute(self, purpose, cleanup_error=False):
        messages=[]
        capture=MagicMock();capture.read.side_effect=lambda:(object(),time.monotonic(),1,(540,900))
        mouse=MagicMock();mouse.size=(540,900)
        if cleanup_error:mouse.close.side_effect=OSError('cleanup failed')
        observation=Observation('waiting',(0,0),(0,0),(0,0),(0,0))
        with patch('fishing.runner.WindowCapture',return_value=capture), patch('fishing.runner.Mouse',return_value=mouse), patch('fishing.runner.Vision') as vision, patch('fishing.runner.user32') as win, patch('fishing.runner.Engine.step',return_value=Action('stop',message='test stop',purpose=purpose)):
            vision.return_value.observe.return_value=observation
            win.GetAsyncKeyState.return_value=0;win.GetForegroundWindow.return_value=42
            run(42,Settings(mode='foreground'),threading.Event(),messages.append)
        flags={}
        for message in messages:
            if isinstance(message,dict):flags.update(message)
        return flags
    def test_normal_stop_is_explicit(self):
        self.assertTrue(self.execute('auto_stop')['normalStop'])
    def test_error_and_cleanup_error_are_not_normal(self):
        self.assertFalse(self.execute('')['normalStop'])
        self.assertFalse(self.execute('auto_stop',True)['normalStop'])
