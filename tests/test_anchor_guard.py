import os
import unittest
from unittest.mock import MagicMock,patch
from fishing.anchor_guard import anchor_centers,unsafe_overlay
from fishing.maa_input import MaaInput

class AnchorGuardTests(unittest.TestCase):
    def test_origin_matches_sdk_and_skips_game(self):
        self.assertEqual(anchor_centers((0,0,1920,1080),(1300,40,1800,1000)),(10,10))
        self.assertEqual(anchor_centers((0,0,1920,1080),(0,0,100,100)),(1910,10))
    def test_negative_monitor_origin(self):
        self.assertEqual(anchor_centers((-1920,0,3840,1080),(0,0,100,100)),(-1910,10))
    def test_myfinder_and_topmost_overlay_rejected(self):
        self.assertTrue(unsafe_overlay('MyFinderApp','MyFinderApp',False))
        self.assertTrue(unsafe_overlay('OtherOverlay','OtherOverlay',True))
    def test_desktop_and_owned_anchor_allowed(self):
        self.assertFalse(unsafe_overlay('WorkerW','Progman',False))
        name=f'MaaAnchoredTouch_{os.getpid()}_123'
        self.assertFalse(unsafe_overlay(name,name,True))
    def test_foreign_anchor_not_treated_as_owned(self):
        self.assertTrue(unsafe_overlay('MaaAnchoredTouch_0_123','MaaAnchoredTouch_0_123',True))
    def test_rejected_anchor_submits_no_touch(self):
        backend=MaaInput.__new__(MaaInput);backend.hwnd=1;backend.mode='background';backend.controller=MagicMock()
        with patch('fishing.anchor_guard.check_anchor',side_effect=RuntimeError('anchor blocked')):
            with self.assertRaisesRegex(RuntimeError,'anchor blocked'):backend.down(10,20)
        backend.controller.post_touch_down.assert_not_called()
