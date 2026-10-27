import unittest
import cv2
from fishing.engine import Engine,Settings
from fishing.vision import Observation,Vision
from fishing.paths import ASSETS

def sample(value,state='ready'):
    return Observation(state,(270,800),(0,0),(0,0),(0,0),multiplier=1,remaining_rods=value,in_yellow=True)

class RemainingRodTests(unittest.TestCase):
    def test_zero_stops_before_cast_bait_or_multiplier(self):
        e=Engine(Settings(auto_bait=True,desired_multiplier=50))
        self.assertEqual(e.step(sample(0),1).kind,'wait')
        self.assertEqual(e.step(sample(0),1.5).kind,'stop')
        self.assertIsNone(e.bait_phase);self.assertIsNone(e.pending_multiplier)
    def test_unknown_or_positive_interrupts_zero_confirmation(self):
        for value in (None,1,100):
            e=Engine(Settings(desired_multiplier=1))
            e.step(sample(0),1);e.step(sample(value),1.2)
            self.assertIsNone(e.rods_zero_since)
            self.assertEqual(e.step(sample(0),1.5).kind,'wait')
    def test_last_rod_is_allowed_to_finish_current_fish(self):
        e=Engine(Settings())
        self.assertEqual(e.step(sample(0,'fight'),1).purpose,'fight')
        self.assertIsNone(e.rods_zero_since)
        e.step(sample(0,'result'),2)
        self.assertEqual(e.step(sample(0),3).kind,'wait')
        self.assertEqual(e.step(sample(0),3.5).kind,'stop')
    def test_real_counter_excludes_rod_icon(self):
        for name,value in (('multiplier-max',491),('ready100',1658)):
            v=Vision();frame=cv2.imread(str(ASSETS/'fixtures'/f'{name}.png'))
            v.observe(frame)
            self.assertEqual(v.read_remaining_rods(v.normalize(frame)),value)
