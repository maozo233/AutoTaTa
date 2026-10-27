import unittest
from fishing.engine import Engine, Settings
from fishing.vision import Observation

def obs(state='ready', multiplier=1, timer='absent', bait=True, inside=False):
    return Observation(state, (270,800), (365,770), (480,765), (270,800), multiplier, bait, timer, inside)

class EngineTests(unittest.TestCase):
    def test_positive_max_toast_resolves_unchanged_multiplier(self):
        e=Engine(Settings(desired_multiplier=50))
        a=e.check_multiplier(obs(multiplier=20),1)
        self.assertEqual(a.kind,'click')
        sample=obs(multiplier=20);sample.multiplier_max=True
        self.assertIsNone(e.check_multiplier(sample,1.1))
        self.assertTrue(e.multiplier_done);self.assertEqual(e.target,20)
        self.assertIsNone(e.pending_multiplier)
    def test_max_toast_does_not_override_lower_desired(self):
        e=Engine(Settings(desired_multiplier=5))
        sample=obs(multiplier=20);sample.multiplier_max=True
        self.assertEqual(e.check_multiplier(sample,1).kind,'click')
        self.assertFalse(e.multiplier_done)
    def test_max_toast_with_unreadable_value_never_casts(self):
        e=Engine(Settings(desired_multiplier=50))
        sample=obs(multiplier=None);sample.multiplier_max=True
        self.assertEqual(e.check_multiplier(sample,1).kind,'wait')
        self.assertFalse(e.multiplier_done)

    def test_fight_one_ms_cooldown_and_round_survives_animation(self):
        e=Engine(Settings())
        for now,state,inside in ((1,'fight',True),(1.001,'fight',True),(1.002,'unknown',False),(1.003,'purple_wait',False),(1.004,'fight',True)):
            action=e.step(obs(state,inside=inside),now)
            if state=='fight':self.assertEqual(action.purpose,'fight')
        self.assertEqual((e.fight_round,e.fight_clicks),(1,3))
        self.assertEqual(e.step(obs('fight',inside=True),1.0045).kind,'wait')
        e.step(obs('result'),2)
        e.step(obs('ready'),3)
        e.step(obs('fight',inside=False),4)
        self.assertEqual((e.fight_round,e.fight_clicks),(2,0))
        action=e.step(obs('fight',inside=True),4.001)
        self.assertIn('第2轮，第1次点击',action.message)


    def test_first_fight_click_is_not_delayed_by_hook_cooldown(self):
        engine=Engine(Settings())
        self.assertEqual(engine.step(obs('hook'), 1).kind, 'click')
        self.assertEqual(engine.step(obs('fight', inside=True), 1.02).kind, 'click')
        self.assertEqual(engine.step(obs('fight', inside=True), 1.07).kind, 'click')
        self.assertEqual(engine.step(obs('fight', inside=False), 1.20).kind, 'wait')
        self.assertEqual(engine.step(obs('fight', inside=True), 1.21).kind, 'click')

    def test_startup_unknown_frame_gets_real_grace_period(self):
        engine=Engine(Settings())
        self.assertEqual(engine.step(obs('unknown'), 100000).kind,'wait')
        self.assertEqual(engine.step(obs('unknown'), 100011).kind,'wait')
        self.assertEqual(engine.step(obs('unknown'), 100013).kind,'stop')

    def test_multiplier_animation_missing_read_does_not_stop(self):
        e = Engine(Settings(desired_multiplier=2))
        e.step(obs(), 0)
        self.assertEqual(e.step(obs(), .6).point, (365,770))
        self.assertEqual(e.step(obs(multiplier=None), 1.1).kind, 'wait')
        self.assertEqual(e.step(obs(multiplier=None), 1.3).kind, 'wait')
        self.assertEqual(e.step(obs(multiplier=2), 1.5).message, '抛竿')

    def test_multiplier_unreadable_for_long_time_stops(self):
        e = Engine(Settings())
        e.step(obs(), 0)
        self.assertEqual(e.step(obs(multiplier=None), .6).kind, 'wait')
        self.assertEqual(e.step(obs(multiplier=None), 2.7).kind, 'stop')


    def menu(self, timer='absent'):
        sample = obs('bait_menu', timer=timer)
        sample.bait_confirm_point = (425,600)
        sample.dismiss_point = (270,540)
        return sample





    def test_manual_popup_does_not_spend_bait(self):
        e = Engine(Settings(auto_bait=True))
        self.assertEqual(e.step(self.menu(), 1).kind, 'stop')
        self.assertEqual(e.bait_used, 0)




    def test_choose_maximum_when_50_unavailable(self):
        e = Engine(Settings(desired_multiplier=50))
        e.step(obs(), 0)
        values = [1,2,3,5,10,20,1,2,3,5,10,20]
        actions = [e.step(obs(multiplier=v), (i+1)*.6) for i,v in enumerate(values)]
        self.assertEqual(actions[-1].message, '抛竿')
        self.assertTrue(all(a.point == (365,770) for a in actions[:-1]))

    def test_reach_requested_multiplier_without_extra_cycle(self):
        e = Engine(Settings(desired_multiplier=3))
        e.step(obs(), 0)
        for i,v in enumerate([1,2,3]):
            a = e.step(obs(multiplier=v), (i+1)*.6)
        self.assertEqual(a.message, '抛竿')

    def test_start_above_requested(self):
        e = Engine(Settings(desired_multiplier=5))
        e.step(obs(), 0)
        for i,v in enumerate([100,1,2,3,5]):
            a = e.step(obs(multiplier=v), (i+1)*.6)
        self.assertEqual(a.message, '抛竿')

    def test_no_click_outside_yellow(self):
        e = Engine(Settings())
        self.assertEqual(e.step(obs('fight', inside=False), 1).kind, 'wait')
        self.assertEqual(e.step(obs('fight', inside=True), 2).kind, 'click')
        self.assertEqual(e.step(obs('fight', inside=True), 2.05).kind, 'click')

    def test_waiting_never_clicks(self):
        self.assertEqual(Engine(Settings()).step(obs('waiting'), 1).kind, 'wait')


    def test_no_timer_check_during_fight(self):
        e = Engine(Settings(stop_on_bait_end=True))
        self.assertEqual(e.step(obs('fight', timer='absent', inside=True), 2).kind, 'click')




    def test_results_low_speed(self):
        e = Engine(Settings())
        self.assertEqual(e.step(obs('result'), 1).kind, 'click')
        self.assertEqual(e.step(obs('result'), 1.2).kind, 'wait')
        self.assertEqual(e.step(obs('result'), 2).kind, 'click')
        self.assertEqual(e.catch_count, 1)

    def test_unresponsive_multiplier_stops(self):
        e = Engine(Settings())
        e.step(obs(multiplier=10), 0)
        e.step(obs(multiplier=10), .6)
        self.assertEqual(e.step(obs(multiplier=10), 3).kind, 'stop')

if __name__ == '__main__':
    unittest.main()
