import unittest
from fishing.engine import Engine,Settings,Action
from fishing.vision import Observation

def obs(state='ready'):
    return Observation(state,(270,800),(365,770),(480,765),(270,600),multiplier=1)

class CastFeedbackTests(unittest.TestCase):
    def test_one_adb_retry_then_failure_no_extra_rods(self):
        e=Engine(Settings(mode='mumu_sdk',desired_multiplier=1))
        e.acknowledge(Action('click',obs().button,purpose='cast',rods=1),0)
        self.assertEqual(e.step(obs(),1).kind,'wait')
        self.assertEqual(e.step(obs(),2.1).purpose,'cast_fallback')
        self.assertEqual(e.step(obs(),3).kind,'wait')
        self.assertEqual(e.step(obs(),5.1).kind,'stop')
        self.assertEqual(e.pending_rods,1);self.assertEqual(e.rods_used,0)
    def test_waiting_confirms_exactly_one_cast(self):
        e=Engine(Settings(mode='mumu_sdk'))
        e.acknowledge(Action('click',obs().button,purpose='cast',rods=1),0)
        e.step(obs('waiting'),.5);e.step(obs('waiting'),1)
        self.assertIsNone(e.cast_submitted_at);self.assertEqual(e.rods_used,1)
    def test_upgrade_hint_is_dismissed_without_cast(self):
        e=Engine(Settings(desired_multiplier=1));o=obs();o.multiplier=None;o.rod_upgrade_hint=True
        a=e.step(o,5);self.assertEqual(a.purpose,'dismiss_upgrade_hint')
        self.assertEqual(a.point,o.dismiss_point);self.assertEqual(e.rods_used,0)
