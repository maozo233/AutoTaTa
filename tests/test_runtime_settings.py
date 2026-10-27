import queue
import unittest
from fishing.engine import Engine, Settings
from fishing.runner import apply_multiplier_updates
from fishing.vision import Observation

def obs(state='ready', value=1, inside=False):
    return Observation(state,(270,800),(365,770),(480,765),(270,800),multiplier=value,in_yellow=inside)

class RuntimeMultiplierTests(unittest.TestCase):
    def test_change_during_fight_applies_only_before_next_cast(self):
        engine=Engine(Settings(desired_multiplier=1))
        engine.bait_used=2
        engine.catch_count=4
        engine.step(obs('fight'),0)
        engine.update_desired_multiplier(3)
        action=engine.step(obs('fight',inside=True),.6)
        self.assertEqual(action.point,(270,800))
        engine.step(obs(),1)
        self.assertEqual(engine.step(obs(),1.5).point,(365,770))
        self.assertEqual(engine.step(obs(value=2),2.1).point,(365,770))
        self.assertEqual(engine.step(obs(value=3),2.7).message,'抛竿')
        self.assertEqual(engine.bait_used,2)
        self.assertEqual(engine.catch_count,4)

    def test_change_keeps_inflight_click_and_prevents_double_click(self):
        engine=Engine(Settings(desired_multiplier=50))
        engine.step(obs(),0)
        self.assertEqual(engine.step(obs(),.6).point,(365,770))
        engine.update_desired_multiplier(3)
        self.assertEqual(engine.step(obs(),1.1).kind,'wait')
        self.assertEqual(engine.step(obs(value=2),1.3).point,(365,770))
        self.assertEqual(engine.step(obs(value=3),1.9).message,'抛竿')

    def test_new_target_clears_previous_maximum_fallback(self):
        engine=Engine(Settings(desired_multiplier=50))
        engine.target=20
        engine.seen=[1,2,3,5,10,20]
        engine.multiplier_done=True
        engine.update_desired_multiplier(3)
        self.assertIsNone(engine.target)
        self.assertFalse(engine.multiplier_done)
        self.assertEqual(engine.seen,[])

    def test_latest_queued_selection_wins(self):
        engine=Engine(Settings(desired_multiplier=1))
        updates=queue.Queue()
        for value in [3,50,20]:updates.put(value)
        self.assertTrue(apply_multiplier_updates(engine,updates))
        self.assertEqual(engine.settings.desired_multiplier,20)
        self.assertTrue(updates.empty())
        self.assertFalse(apply_multiplier_updates(engine,updates))

    def test_runtime_budgets_and_toggles_preserve_counters(self):
        e=Engine(Settings());e.rods_used=120;e.bait_used=2
        q=queue.Queue();q.put({'rod_budget':100,'bait_limit':2,'auto_bait':True,'stop_on_bait_end':True,'full_bait_protection':True})
        apply_multiplier_updates(e,q)
        self.assertEqual((e.settings.rod_budget,e.settings.bait_limit),(100,2))
        self.assertEqual((e.rods_used,e.bait_used),(120,2))
        self.assertTrue(e.settings.full_bait_protection);self.assertTrue(e.settings.auto_bait);self.assertTrue(e.settings.stop_on_bait_end)
        e.ready_since=0
        self.assertEqual(e.step(obs(),2).purpose,'auto_stop')

    def test_crop_changes_coalesce_until_ready(self):
        e=Engine(Settings());q=queue.Queue()
        q.put({'crop_top':10});q.put({'crop_top':20,'crop_bottom':30})
        apply_multiplier_updates(e,q)
        self.assertEqual(e.settings.crop_top,0)
        self.assertEqual(e.runtime_pending,{'crop_top':20,'crop_bottom':30})

    def test_invalid_multiplier_preserves_current_target(self):
        engine=Engine(Settings(desired_multiplier=5))
        with self.assertRaises(ValueError):engine.update_desired_multiplier(7)
        self.assertEqual(engine.settings.desired_multiplier,5)

if __name__=='__main__':unittest.main()
