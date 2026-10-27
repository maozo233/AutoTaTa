import unittest
from fishing.engine import Engine,Settings
from fishing.vision import Observation


def obs(state='ready', value=50):
    return Observation(state,(270,800),(365,770),(480,765),(270,800),multiplier=value,in_yellow=True)


class RodBudgetTests(unittest.TestCase):
    def ready_action(self,engine,value=50,start=0):
        engine.step(obs(value=value),start)
        return engine.step(obs(value=value),start+.6)

    def test_next_cast_cannot_exceed_remaining_budget(self):
        engine=Engine(Settings(desired_multiplier=50,rod_budget=120))
        engine.rods_used=100
        action=self.ready_action(engine)
        self.assertEqual(action.kind,'stop')
        self.assertIn('20',action.message)
        self.assertEqual(engine.rods_used,100)

    def test_exact_budget_completes_current_fish_then_stops(self):
        engine=Engine(Settings(desired_multiplier=50,rod_budget=50))
        action=self.ready_action(engine)
        self.assertEqual(action.purpose,'cast')
        engine.acknowledge(action,.7)
        engine.step(obs('waiting'),.8)
        self.assertEqual(engine.step(obs('fight'),1).kind,'click')
        self.assertEqual(engine.step(obs('result'),2).kind,'click')
        self.assertEqual(self.ready_action(engine,start=3).kind,'stop')
        self.assertEqual(engine.rods_used,50)

    def test_budget_zero_keeps_unlimited_behavior(self):
        engine=Engine(Settings(desired_multiplier=50,rod_budget=0))
        engine.rods_used=99999
        self.assertEqual(self.ready_action(engine).purpose,'cast')

    def test_actual_available_multiplier_is_used(self):
        engine=Engine(Settings(desired_multiplier=50,rod_budget=20))
        engine.target=20
        self.assertEqual(self.ready_action(engine,value=20).purpose,'cast')

    def test_runtime_multiplier_change_cannot_exceed_budget(self):
        engine=Engine(Settings(desired_multiplier=1,rod_budget=10))
        engine.rods_used=4
        engine.update_desired_multiplier(10)
        self.assertEqual(self.ready_action(engine,value=10).kind,'stop')

    def test_no_bait_when_next_cast_cannot_fit(self):
        engine=Engine(Settings(desired_multiplier=50,rod_budget=10,auto_bait=True))
        action=self.ready_action(engine)
        self.assertEqual(action.kind,'stop')
        self.assertIsNone(engine.bait_phase)

    def test_unconfirmed_cast_reserves_budget(self):
        engine=Engine(Settings(desired_multiplier=1,rod_budget=1))
        action=self.ready_action(engine,value=1)
        engine.acknowledge(action,.7)
        self.assertEqual(self.ready_action(engine,value=1,start=1).kind,'wait')
        self.assertEqual(self.ready_action(engine,value=1,start=6).kind,'stop')
        self.assertEqual(engine.rods_used,0)
        self.assertEqual(engine.pending_rods,1)
