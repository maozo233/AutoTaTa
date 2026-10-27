import unittest
from unittest.mock import patch
import cv2
import numpy as np
from fishing.paths import ASSETS
from fishing.display_probe import parse_displays,choose_fishing_display

class ProbeTests(unittest.TestCase):
    def ready(self):return cv2.imread(str(ASSETS/'fixtures/ready.png'))
    def test_android_displays_and_focused_packages(self):
        text="Display: mDisplayId=0\n mCurrentFocus=Window{abc u0 app.home/.Main}\nDisplay: mDisplayId=2\n mFocusedApp=ActivityRecord{def u0 com.game/.Main t1}"
        self.assertEqual(parse_displays(text),{0:'app.home',2:'com.game'})
    def test_unique_fishing_ui_selects_display_two(self):
        ready=self.ready()
        with patch('fishing.vision.Vision.read_multiplier',return_value=2):
            result=choose_fishing_display([(0,np.zeros_like(ready)),(2,ready)])
        self.assertEqual(result,(2,ready.shape[1],ready.shape[0],2))
    def test_multiple_matching_displays_refused(self):
        with self.assertRaisesRegex(RuntimeError,'多个显示区'):
            choose_fishing_display([(0,self.ready()),(2,self.ready())])
    def test_no_fishing_ui_refused(self):
        with self.assertRaisesRegex(RuntimeError,'未找到'):
            choose_fishing_display([(0,np.zeros_like(self.ready()))])
    def test_unreadable_multiplier_refused(self):
        with patch('fishing.vision.Vision.read_multiplier',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'倍率不清晰'):choose_fishing_display([(2,self.ready())])
