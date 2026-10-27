import unittest
from unittest.mock import patch, MagicMock
from fishing.engine import Settings
from fishing.runner import run
from fishing.vision import Observation

class SlowReadyOcrTests(unittest.TestCase):
    def execute(self, *, rods=100, changed_state=None, stale_recovery=False):
        clock=[100.]; frames=[0]; canceled=[False]; last_capture=[0.]
        class Cancel:
            def wait(self, delay):
                clock[0]+=.1
                return canceled[0] or frames[0]>=35
            def is_set(self):return canceled[0]
            def set(self):canceled[0]=True
        capture=MagicMock();capture.size=(540,900)
        def read():
            frames[0]+=1
            last_capture[0]=clock[0]-(.9 if stale_recovery and frames[0]>1 else 0)
            return object(),last_capture[0],frames[0],capture.size
        capture.read.side_effect=read
        clicks=[]
        def click(point):
            clicks.append((point,clock[0]-last_capture[0]));canceled[0]=True
        capture.click.side_effect=click
        vision=MagicMock()
        def observe(frame):
            state=changed_state if frames[0]>1 and changed_state else 'ready'
            return Observation(state,(270,800),(365,770),(480,765),(270,600))
        vision.observe.side_effect=observe
        def slow_rods(game):clock[0]+=.45;return rods
        vision.read_remaining_rods.side_effect=slow_rods
        def slow_multiplier(game):clock[0]+=.45;return 1
        vision.read_multiplier.side_effect=slow_multiplier
        vision.read_rod_level.return_value=3;vision.read_luck.side_effect=lambda game: (clock.__setitem__(0,clock[0]+.45) or 3)
        messages=[]
        with patch('fishing.runner.time.monotonic',side_effect=lambda:clock[0]),patch('fishing.generic_adb.GenericAdbSession',return_value=capture),patch('fishing.runner.Vision',return_value=vision),patch('fishing.runner.user32') as win:
            win.GetAsyncKeyState.return_value=0
            run(42,Settings(mode='maatouch',desired_multiplier=1,rod_budget=1),Cancel(),messages.append)
        return clicks,messages,frames[0]
    def test_slow_ready_ocr_eventually_casts_on_fresh_frame(self):
        clicks,messages,frames=self.execute()
        self.assertEqual([p for p,age in clicks],[(270,800)])
        self.assertTrue(all(age<.8 for _,age in clicks))
        self.assertLess(frames,35)
        self.assertTrue(any(isinstance(m,str) and '数字识别较慢' in m for m in messages))
    def test_zero_rods_remain_a_stop_even_after_slow_ocr(self):
        clicks,messages,_=self.execute(rods=0)
        self.assertFalse(clicks)
        self.assertIn({'normalStop':True},messages)
    def test_changed_screen_does_not_use_ready_decision(self):
        clicks,messages,_=self.execute(changed_state='waiting')
        self.assertFalse(clicks)
        self.assertTrue(any(isinstance(m,str) and '等待咬杆' in m for m in messages))
    def test_recovery_frame_must_still_be_fresh(self):
        clicks,_,_=self.execute(stale_recovery=True)
        self.assertFalse(clicks)
