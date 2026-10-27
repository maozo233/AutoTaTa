import unittest
from unittest.mock import patch
import cv2
import numpy as np
from fishing.vision import Vision
from fishing.paths import ASSETS
from fishing.bait import BaitMaintenance
from fishing.engine import Settings,Action
from fishing.vision import Observation

class RecognitionSourceTests(unittest.TestCase):
    def load(self,name):
        v=Vision();return v,v.normalize(cv2.imread(str(ASSETS/'fixtures'/f'{name}.png')))
    def test_colours_outside_main_button_cannot_change_grade(self):
        v,g=self.load('gold-ready-sdk-real');h=g.shape[0]
        changed=np.full_like(g,(0,0,255))
        changed[h-168:h-40,206:334]=g[h-168:h-40,206:334]
        self.assertEqual(v.read_rod_level(changed),3)
    def test_purple_fight_button_cannot_supply_rod_grade(self):
        v,g=self.load('gold-ready-sdk-real');h=g.shape[0]
        hsv=cv2.cvtColor(g,cv2.COLOR_BGR2HSV);roi=hsv[h-168:h-40,206:334]
        green=(roi[:,:,0]>=35)&(roi[:,:,0]<=85)&(roi[:,:,1]>100)
        roi[:,:,0][green]=145
        self.assertIsNone(v.read_rod_level(cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR)))
    def test_luck_is_independent_of_rod_colour(self):
        v,g=self.load('gold-ready-sdk-real');_,wood=self.load('ready100')
        h=g.shape[0];wh=wood.shape[0]
        g[h-188:h-132,22:86]=wood[wh-188:wh-132,22:86]
        self.assertEqual(v.read_rod_level(g),3)
        self.assertEqual(v.read_luck(g),1)
    def test_clover_number_ignores_timer_and_other_numbers(self):
        v,g=self.load('gold-ready-sdk-real');h=g.shape[0]
        changed=np.zeros_like(g);changed[h-188:h-132,22:86]=g[h-188:h-132,22:86]
        cv2.putText(changed,'8 100 999',(80,h-125),cv2.FONT_HERSHEY_SIMPLEX,1,(255,255,255),2)
        self.assertEqual(v.read_luck(changed),4)
    def test_absent_clover_is_unknown_not_inferred(self):
        v,g=self.load('gold-ready-sdk-real');h=g.shape[0];g[h-188:h-132,22:86]=0
        with patch.object(v,'read_text',return_value='7') as ocr:
            self.assertIsNone(v.read_luck(g));ocr.assert_not_called()
    def test_non_ready_real_screens_have_no_rod_grade(self):
        for name in ('waiting','hook','fight-inside','fight-outside','result'):
            v,g=self.load('ready')
            g=v.normalize(cv2.imread(str(ASSETS/'fixtures'/f'{name}.png')))
            self.assertIsNone(v.read_rod_level(g),name)
    def sample(self,b,t,level=None,luck=4,available=True,motion=False):
        o=Observation('ready',(270,800),(360,750),(480,765),(270,600),rod_level=level,luck=luck,bait_stock=5 if available else 0,bait_available=available,bait_motion=motion,bait_sample_at=t)
        b.observe(o,t);return o
    def test_confirmed_clover_reading_survives_uncertain_rod(self):
        b=BaitMaintenance(Settings(auto_bait=True))
        for t in (0,.4,.8):o=self.sample(b,t)
        self.assertEqual(b.current,4);self.assertIsNone(b.level);self.assertFalse(b.fresh)
        self.assertEqual(b.action(o,.8,Action,ready=True).kind,'wait');self.assertIsNone(b.phase)
    def test_inconsistent_readings_do_not_trigger_bait(self):
        b=BaitMaintenance(Settings(auto_bait=True))
        for t in (0,.4,.8):o=self.sample(b,t,level=1,luck=7)
        self.assertEqual(b.current,7);self.assertFalse(b.fresh)
        self.assertEqual(b.action(o,.8,Action,ready=True).kind,'wait');self.assertIsNone(b.phase)
    def test_no_icon_and_uncertain_grade_does_not_block_fishing(self):
        b=BaitMaintenance(Settings(auto_bait=True));b.deadline=30
        o=self.sample(b,0,available=False)
        self.assertIsNone(b.action(o,0,Action,ready=True));self.assertIsNone(b.deadline)
    def test_stop_policy_still_requires_confirmed_luck(self):
        for policy in ('stop_on_bait_end','stop_when_buffs_end'):
            b=BaitMaintenance(Settings(**{policy:True}))
            o=self.sample(b,0,available=False)
            self.assertEqual(b.action(o,0,Action,ready=True).kind,'wait')
