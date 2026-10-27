import unittest
from fishing.cursor_trace import is_corner_jump

class CursorTraceTests(unittest.TestCase):
    def test_corner_teleport_is_logged_candidate(self):
        self.assertTrue(is_corner_jump((900,600),(10,10),(0,0,1920,1080)))
    def test_normal_movement_is_not_candidate(self):
        self.assertFalse(is_corner_jump((10,10),(12,13),(0,0,1920,1080)))
        self.assertFalse(is_corner_jump((900,600),(400,300),(0,0,1920,1080)))
    def test_negative_monitor_origin_supported(self):
        self.assertTrue(is_corner_jump((100,200),(-1910,10),(-1920,0,3840,1080)))
