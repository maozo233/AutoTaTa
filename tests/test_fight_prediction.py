import unittest
from fishing.engine import Engine,Settings
from fishing.vision import Observation

def sample(x,zone=(100,150),track=(0,540)):
    return Observation('fight',(270,800),(0,0),(0,0),(0,0),float_x=x,yellow=zone,track_bounds=track,in_yellow=zone[0]+1<=x<=zone[1]-1)

class PredictionTests(unittest.TestCase):
    def test_early_region_is_clipped_to_track(self):
        for before,x,zone,track in ((90,97,(100,150),(98,160)),(160,153,(100,150),(90,152))):
            e=Engine(Settings());e.step(sample(before,zone,track),1)
            self.assertEqual(e.step(sample(x,zone,track),1.04).kind,'wait')
        e=Engine(Settings());e.step(sample(95,track=(98,160)),1)
        self.assertEqual(e.step(sample(99,track=(98,160)),1.04).kind,'click')
    def test_missing_or_invalid_track_disables_prediction(self):
        for track in (None,(-1,540),(100,99),(0,541),(110,140)):
            e=Engine(Settings());e.step(sample(80,track=track),1)
            self.assertEqual(e.step(sample(85,track=track),1.04).kind,'wait')

    def test_both_approach_edges_click_before_entry(self):
        for before,x in ((80,86),(170,164)):
            e=Engine(Settings());e.step(sample(before),1)
            action=e.step(sample(x),1.04)
            self.assertEqual(action.kind,'click');self.assertTrue(e.fight_early)
            self.assertIn('提前14px',action.message)
    def test_first_frame_far_stationary_or_moving_away_waits(self):
        for before,x in ((80,85),(170,165),(87,86),(163,164),(86,86),(75,80),(175,170)):
            e=Engine(Settings());self.assertEqual(e.step(sample(before),1).kind,'wait')
            self.assertEqual(e.step(sample(x),1.04).kind,'wait')
    def test_stale_sample_and_zone_jump_do_not_predict(self):
        e=Engine(Settings());e.step(sample(90),1)
        self.assertEqual(e.step(sample(97),1.4).kind,'wait')
        e=Engine(Settings());e.step(sample(80,(80,130)),1)
        self.assertEqual(e.step(sample(97),1.04).kind,'wait')
    def test_entered_yellow_still_clicks_without_motion_history(self):
        e=Engine(Settings());self.assertEqual(e.step(sample(101),1).kind,'click')
        self.assertFalse(e.fight_early)
