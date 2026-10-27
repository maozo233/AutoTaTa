"""OS shortcut sequence checks without opening the system capture overlay."""
import unittest
from unittest.mock import patch
from fishing.windows import start_screen_clip,user32


class ScreenClipTests(unittest.TestCase):
    def test_shortcut_releases_every_key_in_reverse_order(self):
        recorded=[]
        def send(count,events,size):
            recorded.append([(events[i].type,events[i].ki.wVk,events[i].ki.dwFlags) for i in range(count)])
            return count
        with patch.object(user32,'SendInput',side_effect=send):start_screen_clip()
        self.assertEqual(recorded,[[(1,0x5B,1),(1,0x10,0),(1,0x53,0),
                                   (1,0x53,2),(1,0x10,2),(1,0x5B,3)]])
    def test_partial_send_releases_modifiers_before_reporting_failure(self):
        recorded=[]
        def send(count,events,size):
            recorded.append([(events[i].ki.wVk,events[i].ki.dwFlags) for i in range(count)])
            return 2 if len(recorded)==1 else count
        with patch.object(user32,'SendInput',side_effect=send):
            with self.assertRaises(OSError):start_screen_clip()
        self.assertEqual(recorded[1],[(0x53,2),(0x10,2),(0x5B,3)])
