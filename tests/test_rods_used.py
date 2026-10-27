import unittest
from fishing.engine import Engine, Settings
from fishing.vision import Observation


def obs(state='ready', multiplier=1):
    return Observation(state, (270,800), (365,770), (480,765), (270,800), multiplier=multiplier)


class RodUsageTests(unittest.TestCase):
    def cast(self, engine, value, start=0):
        engine.step(obs(multiplier=value), start)
        action=engine.step(obs(multiplier=value), start+.6)
        self.assertEqual(action.purpose, 'cast')
        return action

    def test_count_actual_fallback_multiplier_after_confirmation(self):
        engine=Engine(Settings(desired_multiplier=50))
        engine.target=20
        action=self.cast(engine,20)
        engine.acknowledge(action,.7)
        self.assertEqual(engine.rods_used,0)
        engine.step(obs('waiting'),.8)
        self.assertEqual(engine.rods_used,20)

    def test_failed_or_unconfirmed_click_does_not_count(self):
        engine=Engine(Settings(desired_multiplier=1))
        action=self.cast(engine,1)
        engine.step(obs('waiting'),.8)
        self.assertEqual(engine.rods_used,0)
        engine.acknowledge(action,.9)
        engine.step(obs('unknown'),1)
        self.assertEqual(engine.rods_used,0)

    def test_fight_result_and_runaway_do_not_double_count(self):
        engine=Engine(Settings(desired_multiplier=3))
        action=self.cast(engine,3)
        engine.acknowledge(action,.7)
        for state in ('waiting','hook','fight','fight','result','result','ready'):
            engine.step(obs(state,3),.8)
        self.assertEqual(engine.rods_used,3)
        self.assertEqual(engine.pending_rods,0)

    def test_runtime_multiplier_change_preserves_inflight_usage(self):
        engine=Engine(Settings(desired_multiplier=100))
        action=self.cast(engine,100)
        engine.acknowledge(action,.7)
        engine.update_desired_multiplier(1)
        engine.step(obs('waiting'),.8)
        self.assertEqual(engine.rods_used,100)
        action=self.cast(engine,1,2)
        engine.acknowledge(action,2.7)
        engine.step(obs('waiting'),2.8)
        self.assertEqual(engine.rods_used,101)
        self.assertEqual(Engine(Settings()).rods_used,0)
