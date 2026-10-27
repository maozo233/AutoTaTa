import unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch, MagicMock
import threading
import queue
import time
import cv2
import numpy as np
from rafting.engine import Engine, Settings, Action, REWARDS, MULTIPLIERS
from rafting.vision import Vision, Observation
from fishing.display_probe import choose_feature_display
from tests.qt_ui_case import QtUiCase

ROOT = Path(__file__).resolve().parents[1]


class RaftingEngineTests(unittest.TestCase):
    def test_purchase_stops_even_during_cooldown_or_reward_context(self):
        for purpose in ('spin','choice','panel','reward_button'):
            with self.subTest(purpose=purpose):
                engine=Engine(Settings(desired_multiplier=3,shutdown_on_stop=True))
                engine.after_choice=True
                engine.acknowledge(Action(purpose=purpose),1,3)
                used=engine.used
                action=engine.step(Observation('purchase',dialog_label='漂流艇购买'),1.1)
                self.assertEqual(action.kind,'stop')
                self.assertNotEqual(action.purpose,'auto_stop')
                self.assertIsNone(action.point)
                self.assertEqual(engine.used,used)
                self.assertEqual(engine.completed,0)

    def test_panel_takeover_does_not_create_a_completed_rafting_round(self):
        engine=Engine(Settings(desired_multiplier=3,boat_budget=3))
        engine.step(Observation('unknown',dialog_bounds=(35,120,470,615)),0)
        self.assertFalse(engine.active_round)
        action=engine.step(Observation('panel',dismiss_point=(490,124)),1)
        self.assertEqual(action.purpose,'panel');engine.acknowledge(action,1)
        self.assertFalse(engine.active_round)
        engine.step(self.ready(),2)
        action=engine.step(self.ready(),2.4)
        self.assertEqual(action.purpose,'spin')
        self.assertEqual((engine.completed,engine.used),(0,0))

    def test_confirmed_reward_button_can_be_taken_over_directly(self):
        engine=Engine(Settings())
        obs=Observation('reward_button',dismiss_point=(270,832),reward_context=True,dialog_label='领取奖励')
        action=engine.step(obs,0)
        self.assertEqual(action.point,obs.dismiss_point)
        engine.acknowledge(action,0)
        self.assertEqual(engine.step(obs,2).kind,'wait')
        self.assertEqual(engine.used,0)

    def ready(self, **kw):
        return replace(Observation('ready', (270, 800), (470, 650), multiplier=3, stock=50), **kw)

    def test_maximum_feedback_uses_available_cap(self):
        engine = Engine(Settings(desired_multiplier=50))
        engine.step(self.ready(maximum=True), 0)
        action = engine.step(self.ready(maximum=True), 1)
        self.assertEqual(action.purpose, 'spin')
        self.assertEqual(engine.target, 3)

    def test_nine_tiers_and_budget_boundaries(self):
        self.assertEqual(MULTIPLIERS, (1,2,3,5,10,20,50,100,150))
        for budget,target in [(2,2),(99,50),(100,100),(149,100),(150,150)]:
            engine=Engine(Settings(desired_multiplier=150,boat_budget=budget))
            obs=self.ready(multiplier=target,stock=999)
            engine.step(obs,0);action=engine.step(obs,1)
            self.assertEqual(action.purpose,'spin',(budget,action))
            self.assertEqual(engine.effective_desired,target)
            engine.acknowledge(action,1,target)
            self.assertLessEqual(engine.used,budget)

    def test_full_cycle_reaches_three_digit_tiers_and_cap(self):
        engine=Engine(Settings(desired_multiplier=150))
        for i,value in enumerate(MULTIPLIERS):
            action=engine.multiplier_action(self.ready(multiplier=value),i*3)
            if value==150:self.assertIsNone(action)
            else:
                self.assertEqual(action.purpose,'multiplier')
                engine.acknowledge(action,i*3,value)
        capped=Engine(Settings(desired_multiplier=150))
        self.assertIsNone(capped.multiplier_action(self.ready(multiplier=100,maximum=True),0))
        self.assertEqual(capped.target,100)

    def test_multiplier_redraw_does_not_create_completed_rounds(self):
        engine=Engine(Settings(desired_multiplier=20))
        engine.step(self.ready(multiplier=5),0)
        action=engine.step(self.ready(multiplier=5),1)
        engine.acknowledge(action,1,5)
        action=engine.step(self.ready(multiplier=10,motion=True),2)
        self.assertEqual(action.kind,'wait')
        self.assertFalse(engine.active_round)
        self.assertEqual(engine.completed,0)
        engine.step(self.ready(multiplier=10),2.1)
        action=engine.step(self.ready(multiplier=10),3)
        self.assertEqual(action.purpose,'multiplier')
        engine.acknowledge(action,3,10)
        self.assertEqual(engine.step(self.ready(multiplier=20,motion=True),4).kind,'wait')
        engine.step(self.ready(multiplier=20),4.1)
        action=engine.step(self.ready(multiplier=20),5)
        self.assertEqual(action.purpose,'spin')
        self.assertEqual(engine.completed,0)

    def test_multiplier_animation_timeout_stops_without_spinning(self):
        engine=Engine(Settings(desired_multiplier=20))
        engine.step(self.ready(multiplier=5),0)
        action=engine.step(self.ready(multiplier=5),1);engine.acknowledge(action,1,5)
        action=engine.step(self.ready(multiplier=10,motion=True),10)
        self.assertEqual(action.kind,'stop')
        self.assertEqual(engine.completed,0)

    def test_no_response_is_not_a_maximum(self):
        engine = Engine(Settings(desired_multiplier=50))
        obs = self.ready(multiplier=1)
        engine.step(obs, 0)
        action = engine.step(obs, 1)
        self.assertEqual(action.purpose, 'multiplier')
        engine.acknowledge(action, 1, 1)
        self.assertEqual(engine.step(obs, 4).kind, 'stop')

    def test_cycle_finds_cap_and_runtime_change_resets_target(self):
        engine = Engine(Settings(desired_multiplier=50))
        for time, value in [(0, 3), (3, 5), (6, 1), (9, 3)]:
            action = engine.multiplier_action(self.ready(multiplier=value), time)
            if action:
                engine.acknowledge(action, time, value)
        self.assertEqual(engine.target, 5)
        engine.update({'desired_multiplier': 1})
        self.assertIsNone(engine.target)
        engine.multiplier_pending = None
        self.assertIsNone(engine.multiplier_action(self.ready(multiplier=1), 9))

    def test_submitted_spin_waits_for_animation_and_settlement(self):
        engine = Engine(Settings(desired_multiplier=3))
        obs = self.ready()
        engine.step(obs, 0)
        action = engine.step(obs, 1)
        engine.acknowledge(action, 1, 3)
        self.assertEqual(engine.used, 3)
        self.assertEqual(engine.step(obs, 3).kind, 'wait')
        engine.step(replace(obs, motion=True), 4)
        engine.step(obs, 6)
        engine.step(obs, 9)
        self.assertEqual(engine.completed, 1)
        self.assertFalse(engine.active_round)

    def test_unacknowledged_and_unresponsive_spins_not_repeated(self):
        engine = Engine(Settings(desired_multiplier=3))
        obs = self.ready()
        engine.step(obs, 0)
        action = engine.step(obs, 1)
        self.assertEqual(engine.used, 0)
        engine.acknowledge(action, 1, 3)
        self.assertEqual(engine.step(obs, 12).kind, 'wait')
        self.assertEqual(engine.step(obs, 17).kind, 'wait')
        self.assertEqual(engine.step(obs, 22).kind, 'stop')
        self.assertEqual(engine.used, 3)

    def test_shorter_settlement_reuses_ready_screen_for_next_spin(self):
        engine = Engine(Settings(desired_multiplier=3))
        obs = self.ready()
        engine.step(obs, 0)
        action = engine.step(obs, .4)
        engine.acknowledge(action, .4, 3)
        engine.step(replace(obs, motion=True), 2)
        engine.step(obs, 5.5)
        self.assertEqual(engine.step(obs, 6.2).kind, 'wait')
        self.assertEqual(engine.completed, 0)
        engine.step(obs, 6.5)
        self.assertEqual(engine.completed, 1)
        self.assertEqual(engine.step(obs, 6.6).purpose, 'spin')

    def test_confirmed_unaccepted_paid_spin_retries_twice_on_same_budget(self):
        engine=Engine(Settings(desired_multiplier=3,boat_budget=3))
        obs=self.ready(numbers_fresh=True)
        engine.acknowledge(Action(purpose='spin'),1,3,stock=50)
        for before,confirm,retry in [(9,10,11.1),(19,20,21.2)]:
            engine.step(obs,before);engine.step(obs,confirm)
            action=engine.step(obs,retry)
            self.assertEqual(action.purpose,'spin_retry')
            engine.acknowledge(action,retry,3,stock=50)
            self.assertEqual(engine.used,3)
        self.assertEqual(engine.spin_retries,2)
        self.assertEqual(engine.step(obs,31.3).kind,'stop')
        self.assertEqual(engine.completed,0)

    def test_free_unaccepted_spin_retries_without_boat_cost(self):
        engine=Engine(Settings())
        obs=self.ready(free=True,numbers_fresh=True)
        engine.acknowledge(Action(purpose='spin'),1,0,stock=50,free=True)
        engine.step(obs,9);engine.step(obs,10)
        action=engine.step(obs,11.1)
        self.assertEqual(action.purpose,'spin_retry')
        engine.acknowledge(action,11.1,0,stock=50,free=True)
        self.assertEqual(engine.used,0)
        self.assertEqual(engine.spin_retries,1)

    def test_stock_change_cached_read_or_motion_blocks_repeat_click(self):
        for variant in ('cached','changed','moving'):
            engine=Engine(Settings())
            engine.acknowledge(Action(purpose='spin'),1,3,stock=50)
            obs=self.ready(numbers_fresh=True)
            if variant=='changed':engine.step(self.ready(stock=1231,numbers_fresh=True),8)
            if variant=='moving':engine.observe_progress(self.ready(motion=True),8)
            engine.step(obs,9);engine.step(obs,10)
            action=engine.step(replace(obs,numbers_fresh=variant!='cached'),11.1)
            self.assertNotEqual(action.purpose,'spin_retry',variant)
            self.assertEqual(engine.used,3)


    def test_missed_animation_requires_independent_stock_confirmation(self):
        engine=Engine(Settings(desired_multiplier=3))
        obs=self.ready()
        engine.step(obs,0);action=engine.step(obs,1)
        engine.acknowledge(action,1,3,stock=50)
        spent=self.ready(stock=47,numbers_fresh=True)
        self.assertEqual(engine.step(spent,10.3).kind,'wait')
        self.assertFalse(engine.progress_seen)
        self.assertEqual(engine.step(replace(spent,numbers_fresh=False),11.05).kind,'wait')
        self.assertFalse(engine.progress_seen)
        self.assertEqual(engine.step(spent,11.6).kind,'wait')
        self.assertTrue(engine.progress_seen)
        self.assertEqual(engine.step(spent,12.55).kind,'wait')
        self.assertEqual(engine.completed,1)
        self.assertEqual(engine.used,3)
        self.assertEqual(engine.step(spent,12.65).purpose,'spin')

    def test_wrong_stock_or_free_spin_cannot_confirm_missing_animation(self):
        for cost,before,after in [(3,50,46),(0,50,49)]:
            engine=Engine(Settings(desired_multiplier=3))
            engine.acknowledge(Action(purpose='spin'),1,cost,stock=before)
            obs=self.ready(stock=after,numbers_fresh=True)
            engine.step(obs,9)
            self.assertEqual(engine.step(obs,12).kind,'wait')
            engine.step(obs,17)
            self.assertEqual(engine.step(obs,22).kind,'stop')
            self.assertEqual(engine.completed,0)

    def test_bad_stock_read_recovers_without_confirming_or_retrying(self):
        from rafting.engine import Action
        engine=Engine(Settings(desired_multiplier=3))
        engine.acknowledge(Action(purpose='spin'),1,3,stock=50)
        engine.step(self.ready(stock=47,numbers_fresh=True),10.3)
        action=engine.step(self.ready(stock=50,numbers_fresh=True),11.6)
        self.assertEqual(action.kind,'wait')
        engine.step(self.ready(stock=50,numbers_fresh=True),17)
        self.assertEqual(engine.step(self.ready(stock=50,numbers_fresh=True),22).kind,'stop')
        self.assertFalse(engine.progress_seen)

    def test_consumed_free_turn_confirms_without_boat_cost(self):
        engine=Engine(Settings(desired_multiplier=3,boat_budget=3))
        obs=self.ready(free=True,numbers_fresh=True)
        engine.step(obs,0);action=engine.step(obs,1)
        engine.acknowledge(action,1,0,stock=50,free=True)
        engine.step(self.ready(free=True,numbers_fresh=True),9)
        self.assertFalse(engine.progress_seen)
        paid=self.ready(free=False,numbers_fresh=True)
        engine.step(paid,10.3)
        self.assertEqual(engine.step(replace(paid,numbers_fresh=False),11.1).kind,'wait')
        self.assertFalse(engine.progress_seen)
        engine.step(paid,11.6);engine.step(paid,12.55)
        self.assertEqual(engine.completed,1)
        self.assertEqual(engine.used,0)

    def test_free_label_stays_or_wrong_read_does_not_confirm(self):
        engine=Engine(Settings())
        engine.acknowledge(Action(purpose='spin'),1,0,stock=50,free=True)
        engine.step(self.ready(free=False,numbers_fresh=True),9)
        self.assertEqual(engine.step(self.ready(free=True,numbers_fresh=True),12).kind,'wait')
        engine.step(self.ready(free=True,numbers_fresh=True),17)
        self.assertEqual(engine.step(self.ready(free=True,numbers_fresh=True),22).kind,'stop')
        self.assertFalse(engine.progress_seen)

    def test_free_turn_does_not_require_locked_multiplier_to_change(self):
        engine=Engine(Settings(desired_multiplier=50,boat_budget=3))
        engine.used=3
        obs=self.ready(multiplier=1,stock=0,free=True)
        engine.step(obs,0)
        action=engine.step(obs,1)
        self.assertEqual(action.purpose,'spin')
        engine.acknowledge(action,1,0,stock=0,free=True)
        self.assertEqual(engine.used,3)

    def test_slow_recognition_preserves_motion_without_clicking_stale_frame(self):
        from rafting.engine import Action
        engine=Engine(Settings(desired_multiplier=3))
        engine.acknowledge(Action(purpose='spin'),1,3,stock=50)
        engine.observe_progress(self.ready(motion=True),2)
        self.assertTrue(engine.progress_seen)
        self.assertEqual(engine.completed,0)
        self.assertEqual(engine.step(self.ready(),12).kind,'wait')
        engine.step(self.ready(),13)
        self.assertEqual(engine.completed,1)

    def test_late_boat_movement_or_reward_restarts_short_settlement(self):
        engine = Engine(Settings(desired_multiplier=3))
        obs = self.ready()
        engine.takeover(0)
        engine.step(obs, 5)
        engine.step(replace(obs, motion=True), 5.8)
        engine.step(obs, 6)
        self.assertEqual(engine.step(obs, 6.8).kind, 'wait')
        reward = Observation('reward', dismiss_point=(270, 700))
        action = engine.step(reward, 6.85)
        self.assertEqual(action.purpose, 'dismiss')
        engine.acknowledge(action, 6.85)
        self.assertEqual(engine.step(reward, 7.9).kind, 'wait')
        self.assertEqual(engine.completed, 0)
        engine.step(obs, 8)
        self.assertEqual(engine.step(obs, 8.8).kind, 'wait')
        self.assertEqual(engine.completed, 0)
        engine.step(obs, 8.95)
        self.assertEqual(engine.completed, 1)

    def test_all_six_priorities_and_runtime_reorder(self):
        engine = Engine(Settings())
        obs = Observation('choice', choices=[('coins', (1, 1)), ('capsule', (2, 2)), ('raft', (3, 3))])
        self.assertEqual(engine.step(obs, 0).point, (2, 2))
        order = [r[0] for r in REWARDS]
        order.insert(0, order.pop(order.index('coins')))
        engine.update({'priority': order})
        self.assertEqual(engine.step(obs, 1).point, (1, 1))
        obs.choices[0] = (None, (1, 1))
        self.assertEqual(engine.step(obs, 2).kind, 'wait')
        self.assertEqual(engine.step(obs, 20).kind, 'stop')

    def test_zero_inventory_does_not_stop_and_reward_click_feedback(self):
        engine = Engine(Settings(desired_multiplier=3))
        obs = self.ready(stock=0,numbers_fresh=True)
        engine.step(obs, 0)
        engine.step(obs, 1)
        self.assertEqual(engine.step(obs, 3).purpose, 'spin')
        reward = Observation('reward', dismiss_point=(270, 700))
        action = engine.step(reward, 4)
        self.assertEqual(action.purpose, 'dismiss')
        engine.acknowledge(action, 4)
        self.assertEqual(engine.step(reward, 6).kind, 'wait')
        self.assertEqual(engine.step(reward, 13).kind, 'stop')

    def test_budget_reduces_multiplier_and_waits_for_rewards(self):
        engine=Engine(Settings(desired_multiplier=50,boat_budget=4))
        obs=self.ready()
        engine.step(obs,0)
        action=engine.step(obs,1)
        self.assertEqual(action.purpose,'spin')
        engine.acknowledge(action,1,3)
        engine.step(replace(obs,motion=True),3)
        reward=Observation('confirm',dismiss_point=(200,800))
        action=engine.step(reward,4)
        self.assertEqual(action.purpose,'confirm')
        engine.acknowledge(action,4)
        engine.step(obs,6);engine.step(obs,9)
        action=engine.step(obs,10)
        self.assertEqual(action.purpose,'multiplier')
        self.assertEqual(engine.effective_desired,1)
        engine.acknowledge(action,10,3)
        self.assertEqual(engine.step(replace(obs,multiplier=1),11).purpose,'spin')
        engine.used=4
        action=engine.step(obs,12)
        self.assertEqual(action.purpose,'auto_stop')

    def test_inventory_is_not_a_gate_or_automatic_shutdown_trigger(self):
        engine=Engine(Settings(desired_multiplier=3))
        engine.step(self.ready(stock=None),0)
        for now,stock in enumerate((None,0,1,999),1):
            action=engine.step(self.ready(stock=stock,numbers_fresh=True),now)
            self.assertEqual(action.purpose,'spin',stock)
        self.assertEqual(engine.used,0)

    def test_visual_retries_without_inventory_are_bounded_and_charge_once(self):
        engine=Engine(Settings(desired_multiplier=3,boat_budget=3))
        obs=self.ready(stock=None,visual_signature=b'frame')
        engine.acknowledge(Action(purpose='spin'),1,3,visual_signature=obs.visual_signature)
        for before,confirm,retry in ((9,10,11.1),(19,20,21.2)):
            engine.step(obs,before);engine.step(obs,confirm)
            action=engine.step(obs,retry)
            self.assertEqual(action.purpose,'spin_retry')
            engine.acknowledge(action,retry,3,visual_signature=obs.visual_signature)
        action=engine.step(obs,31.3)
        self.assertEqual((action.kind,action.purpose),('stop',''))
        self.assertEqual(engine.used,3)
        self.assertEqual(engine.completed,0)

    def test_sector_pose_allows_retry_despite_brightness_changes(self):
        engine=Engine(Settings(desired_multiplier=3,boat_budget=3))
        pose=tuple([0,1,2,0]*7)
        obs=self.ready(stock=None,visual_signature=bytes([8])*100,wheel_pose=pose)
        engine.acknowledge(Action(purpose='spin'),1,3,visual_signature=bytes(100),wheel_pose=pose)
        engine.step(obs,9);engine.step(obs,10)
        action=engine.step(obs,11.1)
        self.assertEqual(action.purpose,'spin_retry')
        self.assertFalse(engine.ambiguous_change)
        self.assertEqual(engine.used,3)

    def test_stable_changed_sector_result_confirms_a_missed_rotation(self):
        engine=Engine(Settings(desired_multiplier=3))
        original=tuple([0]*14+[1]*14)
        changed=tuple([1]*14+[0]*14)
        obs=self.ready(stock=None,wheel_pose=changed,visual_signature=b'frame')
        engine.acknowledge(Action(purpose='spin'),1,3,wheel_pose=original,visual_signature=b'frame')
        engine.step(obs,8);engine.step(obs,8.4)
        self.assertTrue(engine.progress_seen)
        engine.step(obs,9.4)
        self.assertEqual(engine.completed,1)
        self.assertEqual(engine.step(obs,9.5).kind,'wait')
        self.assertEqual(engine.step(obs,9.8).purpose,'spin')

    def test_unknown_frame_does_not_confirm_a_submitted_spin(self):
        engine=Engine(Settings(desired_multiplier=3))
        pose=tuple([0,1]*14)
        engine.acknowledge(Action(purpose='spin'),1,3,wheel_pose=pose)
        engine.step(Observation('unknown'),3)
        self.assertFalse(engine.progress_seen)
        self.assertEqual(engine.completed,0)

    def test_changed_visual_without_animation_never_repeats_input(self):
        engine=Engine(Settings(desired_multiplier=3))
        obs=self.ready(stock=None,visual_signature=bytes([30])*100)
        engine.acknowledge(Action(purpose='spin'),1,3,visual_signature=bytes([0])*100)
        for now in (9,10,11.1,17):
            self.assertNotEqual(engine.step(obs,now).purpose,'spin_retry')
        self.assertEqual(engine.step(obs,22).kind,'stop')
        self.assertTrue(engine.ambiguous_change)

    def test_rounds_rewards_free_turn_and_budget_work_with_unreadable_inventory(self):
        engine=Engine(Settings(desired_multiplier=3,boat_budget=3))
        obs=self.ready(stock=None,visual_signature=b'frame')
        engine.step(obs,0);action=engine.step(obs,1)
        engine.acknowledge(action,1,3,visual_signature=obs.visual_signature)
        engine.step(replace(obs,motion=True),2)
        free=replace(obs,free=True)
        engine.step(free,6);engine.step(free,7)
        action=engine.step(free,8)
        self.assertEqual(action.purpose,'spin')
        engine.acknowledge(action,8,0,free=True,visual_signature=free.visual_signature)
        engine.step(replace(free,motion=True),9)
        reward=Observation('choice',choices=[('coins',(1,1)),('wishbox',(2,2)),('raft',(3,3))])
        action=engine.step(reward,10)
        self.assertEqual(action.point,(2,2));engine.acknowledge(action,10)
        engine.step(obs,14);engine.step(obs,15)
        action=engine.step(obs,16)
        self.assertEqual((action.kind,action.purpose),('stop','auto_stop'))
        self.assertEqual((engine.completed,engine.used),(2,3))

    def test_takeover_does_not_charge_existing_round(self):
        for state in ('choice','reward','cardpack','confirm','transition'):
            engine=Engine(Settings(desired_multiplier=3,boat_budget=1))
            obs=Observation(state,dismiss_point=(200,800),choices=[('raft',(1,1)),('coins',(2,2)),('capsule',(3,3))])
            action=engine.step(obs,0)
            if action.kind=='click':engine.acknowledge(action,0)
            self.assertEqual(engine.used,0)
            self.assertTrue(engine.active_round)
            engine.step(self.ready(),2);engine.step(self.ready(),7)
            self.assertEqual(engine.completed,1)
            self.assertEqual(engine.used,0)

    def test_free_spin_and_runtime_budget(self):
        engine=Engine(Settings(desired_multiplier=3,boat_budget=2))
        obs=self.ready(free=True,stock=0)
        engine.step(obs,0);action=engine.step(obs,1)
        self.assertEqual(action.purpose,'spin')
        engine.acknowledge(action,1,0)
        self.assertEqual(engine.used,0)
        engine.update({'boat_budget':1})
        self.assertEqual(engine.settings.boat_budget,1)

    def test_cardpack_requires_accept_and_click_feedback(self):
        engine=Engine(Settings())
        obs=Observation('cardpack',dismiss_point=(245,815))
        action=engine.step(obs,0)
        self.assertEqual(action.point,(245,815))
        self.assertEqual(action.purpose,'cardpack')
        engine.acknowledge(action,0)
        self.assertEqual(engine.step(obs,2).kind,'wait')
        self.assertEqual(engine.step(obs,9).kind,'stop')

    def test_accept_retries_visible_button_at_most_three_times_without_budget(self):
        engine=Engine(Settings())
        obs=Observation('cardpack',dismiss_point=(270,854),dialog_label='开心收下')
        first=engine.step(obs,0);engine.acknowledge(first,0)
        self.assertEqual(engine.step(obs,1).kind,'wait')
        second=engine.step(obs,1.7)
        self.assertEqual((second.purpose,second.point),('cardpack',obs.dismiss_point))
        engine.acknowledge(second,1.7)
        self.assertEqual(engine.step(obs,2.6).kind,'wait')
        third=engine.step(obs,3.4)
        self.assertEqual(third.purpose,'cardpack');engine.acknowledge(third,3.4)
        self.assertEqual(engine.step(obs,5.2).kind,'wait')
        self.assertEqual(engine.step(obs,9).kind,'stop')
        self.assertEqual(engine.cardpack_attempts,3)
        self.assertEqual((engine.used,engine.completed),(0,0))

    def test_accept_retry_requires_stable_current_button_and_stops_on_purchase(self):
        engine=Engine(Settings());original=Observation('cardpack',dismiss_point=(270,854))
        engine.acknowledge(engine.step(original,0),0)
        engine.step(original,1)
        moved=replace(original,dismiss_point=(270,800))
        self.assertEqual(engine.step(moved,2).kind,'wait')
        self.assertEqual(engine.step(moved,2.2).kind,'wait')
        retry=engine.step(moved,2.5)
        self.assertEqual(retry.point,moved.dismiss_point)
        engine.acknowledge(retry,2.5)
        self.assertEqual(engine.step(Observation('unknown'),4.5).kind,'wait')
        self.assertEqual(engine.step(Observation('transition'),4.6).kind,'wait')
        self.assertEqual(engine.pending,'cardpack')
        self.assertEqual(engine.step(moved,4.7).kind,'wait')
        self.assertEqual(engine.step(Observation('purchase'),4.8).kind,'stop')

    def test_capsule_groups_continue_after_transition_or_button_label_change(self):
        engine=Engine(Settings(desired_multiplier=3))
        group=Observation('capsule_group',dismiss_point=(270,854),capsule_label='再开一组')
        action=engine.step(group,0);self.assertEqual(action.purpose,'capsule_group')
        engine.acknowledge(action,0)
        self.assertEqual(engine.step(group,2).kind,'wait')
        generic=Observation('reward_button',dismiss_point=group.dismiss_point)
        self.assertEqual(engine.step(generic,2.05).kind,'wait')
        engine.step(Observation('transition'),2.1)
        self.assertEqual(engine.step(group,2.2).kind,'wait')
        action=engine.step(group,2.7);self.assertEqual(action.purpose,'capsule_group')
        engine.acknowledge(action,2.7)
        all_group=replace(group,capsule_label='开启全部')
        action=engine.step(all_group,4);self.assertEqual(action.purpose,'capsule_group')
        engine.acknowledge(action,4)
        confirm=Observation('confirm',dismiss_point=(270,854))
        action=engine.step(confirm,6);self.assertEqual(action.purpose,'confirm')
        engine.acknowledge(action,6)
        engine.step(self.ready(),8);engine.step(self.ready(),9)
        self.assertEqual(engine.completed,1)
        self.assertEqual(engine.used,0)

    def test_generic_green_button_requires_selected_reward_context(self):
        engine=Engine(Settings(desired_multiplier=3))
        green=Observation('reward_button',dismiss_point=(270,854))
        self.assertEqual(engine.step(green,0).kind,'wait')
        self.assertEqual(engine.step(green,9).kind,'stop')
        engine=Engine(Settings(desired_multiplier=3))
        choice=Observation('choice',choices=[('raft',(1,1)),('capsule',(2,2)),('lunchbox',(3,3))])
        action=engine.step(choice,1);engine.acknowledge(action,1)
        action=engine.step(green,2);self.assertEqual(action.purpose,'reward_button')
        engine.acknowledge(action,2)
        self.assertEqual(engine.step(green,4).kind,'wait')
        engine.step(Observation('transition'),4.1)
        self.assertEqual(engine.step(green,4.2).kind,'wait')
        labeled=replace(green,dialog_label='领取',dialog_checked=True)
        self.assertEqual(engine.step(labeled,4.3).kind,'wait')
        action=engine.step(labeled,4.8);self.assertEqual(action.purpose,'reward_button')
        engine.acknowledge(action,4.8)
        engine.step(self.ready(),8);engine.step(self.ready(),9)
        self.assertFalse(engine.after_choice)
        self.assertEqual(engine.step(green,10).kind,'wait')
        self.assertEqual(engine.step(green,19).kind,'stop')
        self.assertEqual(engine.used,0)

    def test_capsule_animation_timeout_stops_without_more_clicks_or_shutdown(self):
        engine=Engine(Settings())
        group=Observation('capsule_group',dismiss_point=(270,854),capsule_label='再开一组')
        action=engine.step(group,0);engine.acknowledge(action,0)
        self.assertEqual(engine.step(Observation('unknown'),1).kind,'wait')
        action=engine.step(Observation('unknown'),14)
        self.assertEqual((action.kind,action.purpose),('stop',''))

    def test_new_capsule_contents_continue_without_a_counter_or_hidden_button(self):
        vision=Vision();frame=vision.read_image(ROOT/'assets/fixtures/rafting/capsule-batch-5-of-10-sdk.png')
        original=vision.observe(frame,False);engine=Engine(Settings())
        action=engine.step(original,0);engine.acknowledge(action,0)
        retries=0
        animation=sorted((ROOT/'tests/fixtures/rafting/capsule-animation').glob('*.jpg'));self.assertEqual(len(animation),40)
        for index,path in enumerate(animation):
            current=Vision().observe(Vision.read_image(path),False)
            now=1+index*.1;action=engine.step(current,now)
            if action.kind=='click':
                retries+=1;engine.acknowledge(action,now)
        self.assertLessEqual(retries,2)
        self.assertEqual(engine.reward_started,0)
        game=Vision().normalize(frame)
        for cx,cy in ((270,.13),(120,.35),(410,.35),(180,.6),(410,.6)):
            cv2.rectangle(game,(cx-45,round(len(game)*cy)-45),(cx+45,round(len(game)*cy)+45),(255,50,20),-1)
        changed=Vision().observe(game,False)
        self.assertEqual(engine.step(changed,5.5).kind,'wait')
        self.assertEqual(engine.step(changed,6).purpose,'capsule_group')
        self.assertEqual(engine.used,0)

    def test_all_reward_buttons_retry_three_times_without_charging_submitted_budget(self):
        cases=[Observation('confirm',dismiss_point=(270,854),dialog_label='确定',dialog_checked=True),
               Observation('reward_button',dismiss_point=(270,854),dialog_label='领取奖励',dialog_checked=True,reward_context=True),
               Observation('capsule_group',dismiss_point=(270,854),capsule_label='再开一组'),
               Observation('capsule_group',dismiss_point=(410,854),capsule_label='开启全部'),
               Observation('choice',choices=[('raft',(100,640)),('coins',(270,640)),('capsule',(440,640))],dialog_label='选择')]
        for obs in cases:
            with self.subTest(state=obs.state,label=obs.dialog_label or obs.capsule_label):
                engine=Engine(Settings());engine.acknowledge(Action(purpose='spin'),0,multiplier=3)
                first=engine.step(obs,2);engine.acknowledge(first,2,multiplier=50)
                self.assertEqual(first.kind,'click')
                for seen,clicked in ((3,3.7),(4.7,5.4)):
                    self.assertEqual(engine.step(obs,seen).kind,'wait')
                    retry=engine.step(obs,clicked)
                    self.assertEqual((retry.purpose,retry.point),(first.purpose,first.point))
                    self.assertTrue(retry.label)
                    engine.acknowledge(retry,clicked,multiplier=150)
                self.assertEqual(engine.step(obs,7).kind,'wait')
                self.assertEqual(engine.step(obs,11).kind,'stop')
                self.assertEqual((engine.reward_attempts,engine.used,engine.completed),(3,3,0))

    def test_retry_does_not_use_missing_unchecked_or_purchase_label(self):
        engine=Engine(Settings());obs=Observation('confirm',dismiss_point=(270,854),dialog_label='确定',dialog_checked=True)
        engine.acknowledge(engine.step(obs,0),0)
        for now,bad in ((1,replace(obs,dialog_label='')),(2,replace(obs,dialog_checked=False)),(3,replace(obs,dialog_label='购买'))):
            self.assertEqual(engine.step(bad,now).kind,'wait')
        self.assertEqual(engine.step(obs,3.2).kind,'wait')
        self.assertEqual(engine.step(Observation('unknown'),3.7).kind,'wait')
        self.assertEqual(engine.step(obs,4).kind,'wait')
        self.assertEqual(engine.step(Observation('purchase'),4.2).kind,'stop')
        self.assertEqual(engine.reward_attempts,1)

    def test_choice_retry_keeps_selected_reward_and_reads_its_new_position(self):
        engine=Engine(Settings())
        obs=Observation('choice',choices=[('raft',(100,640)),('coins',(270,640)),('capsule',(440,640))],dialog_label='选择')
        action=engine.step(obs,0);engine.acknowledge(action,0)
        engine.update({'priority':['coins','wishbox','stars','capsule','raft','lunchbox']})
        moved=replace(obs,choices=[('raft',(100,700)),('coins',(270,700)),('capsule',(440,700))])
        self.assertEqual(engine.step(moved,2).kind,'wait')
        retry=engine.step(moved,2.5)
        self.assertEqual(retry.point,(440,700))

    def test_consecutive_different_choices_continue(self):
        engine=Engine(Settings())
        obs=Observation('choice',choices=[('raft',(1,1)),('coins',(2,2)),('capsule',(3,3))])
        action=engine.step(obs,0);engine.acknowledge(action,0)
        obs.choices=[('stars',(1,1)),('lunchbox',(2,2)),('capsule',(3,3))]
        self.assertEqual(engine.step(obs,2).purpose,'choice')


class RaftingDisplayReadingsTests(unittest.TestCase):
    def backend(self):
        from PySide6.QtCore import QCoreApplication
        from rafting.backend import RaftingBackend
        self.app=QCoreApplication.instance() or QCoreApplication([])
        b=RaftingBackend(discover=False);b.timer.stop();b.persist=lambda:None
        return b

    def test_missing_values_keep_last_read_and_real_zero_updates(self):
        b=self.backend()
        self.assertIsNone(b.state['stock']);self.assertIsNone(b.state['currentMultiplier'])
        b.update(stock=997,currentMultiplier=50,maximum=True)
        for phase in ('unknown','transition','choice','confirm','ready'):
            b.update(phase=phase,stock=None,currentMultiplier=None,maximum=False)
            self.assertEqual((b.state['stock'],b.state['currentMultiplier'],b.state['maximum']),(997,50,True))
        b.update(stock=0,currentMultiplier=3,maximum=False)
        self.assertEqual((b.state['stock'],b.state['currentMultiplier'],b.state['maximum']),(0,3,False))

    def test_queue_coalescing_does_not_drop_a_new_read_before_missing_frame(self):
        b=self.backend();b.update(stock=997,currentMultiplier=50)
        b.events.put({'stock':991,'currentMultiplier':3,'maximum':True})
        b.events.put({'stock':None,'currentMultiplier':None,'maximum':False,'phase':'confirm'})
        b.poll()
        self.assertEqual((b.state['stock'],b.state['currentMultiplier'],b.state['maximum']),(991,3,True))

    def test_restart_same_device_preserves_display_and_different_device_clears(self):
        b=self.backend();b.entries=[{'hwnd':1},{'hwnd':2}];b.update(devices=['one','two'],deviceIndex=0)
        with patch('rafting.backend.threading.Thread'):
            b.start();b.update(running=False,stock=997,currentMultiplier=50)
            b.start()
            self.assertEqual((b.state['stock'],b.state['currentMultiplier']),(997,50))
            b.update(running=False);b.selectDevice(1)
            self.assertIsNone(b.state['stock']);self.assertIsNone(b.state['currentMultiplier'])
            b.update(stock=997,currentMultiplier=50);b.start()
            self.assertIsNone(b.state['stock']);self.assertIsNone(b.state['currentMultiplier'])

class RaftingInventoryTests(unittest.TestCase):
    def test_pending_inventory_cannot_block_control_and_stale_result_is_hidden(self):
        from concurrent.futures import Future
        from rafting.inventory import InventoryReader
        vision=Vision();frame=vision.read_image(ROOT/'assets/fixtures/rafting/stock-979-sdk.png')
        obs=vision.observe(frame,read_numbers=False)
        future=Future();reader=InventoryReader()
        try:
            with patch.object(reader.pool,'submit',return_value=future) as submit:
                self.assertIsNone(reader.sample(vision,frame,obs,0))
                self.assertIsNone(reader.sample(vision,frame,obs,1))
                submit.assert_called_once()
                future.set_result(979)
                self.assertEqual(reader.sample(vision,frame,obs,2),979)
                changed=frame.copy();game=vision.normalize(changed)
                by=(obs.button[1]-vision.rect[1])*540/(vision.rect[2]-vision.rect[0])
                top=round((by+65)*frame.shape[1]/540)
                changed[top:top+60,330:620]=0
                self.assertIsNone(reader.sample(vision,changed,obs,3))
        finally:
            reader.close()

    def test_inventory_worker_failure_is_only_an_unreadable_display(self):
        from concurrent.futures import Future
        from rafting.inventory import InventoryReader
        vision=Vision();frame=vision.read_image(ROOT/'assets/fixtures/rafting/stock-979-sdk.png')
        obs=vision.observe(frame,read_numbers=False)
        future=Future();reader=InventoryReader()
        try:
            with patch.object(reader.pool,'submit',return_value=future):
                reader.sample(vision,frame,obs,0)
                future.set_exception(RuntimeError('OCR unavailable'))
                self.assertIsNone(reader.sample(vision,frame,obs,1))
        finally:
            reader.close()


class RaftingControlReaderTests(unittest.TestCase):
    def test_confirm_cache_rechecks_current_button_lettering(self):
        from concurrent.futures import Future
        from rafting.controls import ControlReader
        vision=Vision();frame=vision.read_image(ROOT/'assets/fixtures/rafting/confirm-full.png')
        known=vision.observe(frame,True,False);fast=vision.observe(frame,False,False)
        self.assertEqual(known.dialog_label,'确定')
        reader=ControlReader();future=Future()
        try:
            with patch.object(reader.pool,'submit',return_value=future):
                reader.sample(vision,frame,fast,0);reader.sample(vision,frame,fast,.5)
                future.set_result(known)
                self.assertEqual(reader.sample(vision,frame,fast,.7).state,'confirm')
                changed=frame.copy();x,y=map(round,known.dismiss_point)
                changed[y-17:y+18,x-55:x+56]=(30,190,90)
                self.assertEqual(reader.sample(vision,changed,fast,.9).state,'unknown')
        finally:reader.close()

    def test_generic_green_and_confirm_wait_for_purchase_check(self):
        from concurrent.futures import Future
        from rafting.controls import ControlReader
        frame=Vision.read_image(ROOT/'assets/fixtures/rafting/purchase-boat-dark-synthetic.png')
        vision=Vision();purchase=vision.observe(frame,True,False)
        self.assertEqual(purchase.state,'purchase')
        self.assertIsNone(vision.modal_rect(vision.normalize(frame)))
        fast=vision.observe(frame,False,False)
        self.assertIn(fast.state,('reward_button','confirm'))
        for state in ('reward_button','confirm'):
            obs=replace(fast,state=state,dialog_checked=False)
            reader=ControlReader();future=Future();engine=Engine(Settings())
            engine.after_choice=True
            try:
                with patch.object(reader.pool,'submit',return_value=future):
                    checked=reader.sample(vision,frame,obs,0)
                    self.assertEqual(checked.state,'unknown')
                    self.assertNotEqual(engine.step(checked,0).kind,'click')
                    reader.sample(vision,frame,obs,.5);future.set_result(purchase)
                    checked=reader.sample(vision,frame,obs,.7)
                    self.assertEqual(engine.step(checked,.7).kind,'stop')
            finally:reader.close()

    def test_checked_generic_green_keeps_selected_reward_fallback(self):
        from concurrent.futures import Future
        from rafting.controls import ControlReader
        vision=Vision();frame=vision.read_image(ROOT/'assets/fixtures/rafting/reward-button-synthetic.png')
        obs=Observation('reward_button',dismiss_point=(270,832))
        known=replace(obs,dialog_checked=True)
        reader=ControlReader();future=Future();engine=Engine(Settings());engine.after_choice=True
        try:
            with patch.object(reader.pool,'submit',return_value=future):
                self.assertEqual(reader.sample(vision,frame,obs,0).state,'unknown')
                reader.sample(vision,frame,obs,.5);future.set_result(known)
                checked=reader.sample(vision,frame,obs,.7)
                self.assertEqual(engine.step(checked,.7).point,obs.dismiss_point)
        finally:reader.close()

    def test_dialog_cache_ignores_background_but_rejects_changed_or_missing_dialog(self):
        from concurrent.futures import Future
        from rafting.controls import ControlReader
        vision=Vision();frame=vision.read_image(ROOT/'assets/fixtures/rafting/rules-synthetic.png')
        known=vision.observe(frame,True,False);obs=vision.observe(frame,False,False)
        reader=ControlReader();future=Future()
        try:
            with patch.object(reader.pool,'submit',return_value=future):
                reader.sample(vision,frame,obs,0);reader.sample(vision,frame,obs,.5)
                future.set_result(known)
                changed=frame.copy();changed[:80]=120;changed[880:]=120
                self.assertEqual(reader.sample(vision,changed,obs,.7).state,'panel')
                changed[100:147,460:515]=0
                self.assertEqual(reader.sample(vision,changed,obs,.8).state,'unknown')
                purchase=vision.read_image(ROOT/'assets/fixtures/rafting/purchase-boat-text-synthetic.png')
                self.assertEqual(reader.sample(vision,purchase,obs,.9).state,'unknown')
        finally:reader.close()

    def test_purchase_ocr_is_returned_to_a_fast_unknown_observation(self):
        from concurrent.futures import Future
        from rafting.controls import ControlReader
        vision=Vision();frame=vision.read_image(ROOT/'assets/fixtures/rafting/purchase-boat-art-synthetic.png')
        known=vision.observe(frame,True,False);obs=vision.observe(frame,False,False)
        reader=ControlReader();future=Future()
        try:
            with patch.object(reader.pool,'submit',return_value=future):
                reader.sample(vision,frame,obs,0);reader.sample(vision,frame,obs,.5)
                future.set_result(known)
                self.assertEqual(reader.sample(vision,frame,obs,.7).state,'purchase')
        finally:reader.close()

    def test_capsule_button_result_matches_lettering_despite_character_animation(self):
        from concurrent.futures import Future
        from rafting.controls import ControlReader
        for name in ('capsule-batch-5-of-10-sdk','capsule-batch-next-and-all-phone'):
            with self.subTest(fixture=name):
                vision=Vision();frame=vision.read_image(ROOT/f'assets/fixtures/rafting/{name}.png')
                known=vision.observe(frame,False);obs=Observation('unknown')
                reader=ControlReader();future=Future()
                try:
                    with patch.object(reader.pool,'submit',return_value=future):
                        reader.sample(vision,frame,obs,0);reader.sample(vision,frame,obs,.5)
                        future.set_result(known)
                        changed=frame.copy();changed[180:round(len(frame)*.7)]=0
                        result=reader.sample(vision,changed,obs,.7)
                        self.assertEqual(result.state,'capsule_group')
                        self.assertEqual(result.dismiss_point,known.dismiss_point)
                        y=round(known.dismiss_point[1]);changed[y-60:y+60]=0
                        self.assertEqual(reader.sample(vision,changed,obs,.9).state,'unknown')
                finally:reader.close()
    def test_pending_ocr_does_not_block_or_overwrite_current_free_and_motion(self):
        from concurrent.futures import Future
        from rafting.controls import ControlReader
        vision=Vision();frame=vision.read_image(ROOT/'assets/fixtures/rafting/stock-979-sdk.png')
        obs=replace(vision.observe(frame,False),free=True,motion=True)
        reader=ControlReader();future=Future()
        try:
            with patch.object(reader.pool,'submit',return_value=future):
                self.assertIsNone(reader.sample(vision,frame,obs,0).multiplier)
                self.assertIsNone(reader.sample(vision,frame,obs,.2).multiplier)
                future.set_result(Observation('ready',multiplier=20,free=False,motion=False))
                result=reader.sample(vision,frame,obs,.4)
                self.assertEqual(result.multiplier,20)
                self.assertTrue(result.free);self.assertTrue(result.motion)
                changed=frame.copy();changed[980:1100,700:870]=0
                self.assertIsNone(reader.sample(vision,changed,obs,.6).multiplier)
        finally:reader.close()

    def test_unknown_overlay_ocr_is_delayed_and_bound_to_the_same_frame(self):
        from concurrent.futures import Future
        from rafting.controls import ControlReader
        vision=Vision();frame=vision.read_image(ROOT/'assets/fixtures/rafting/stock-979-sdk.png')
        vision.normalize(frame);obs=Observation('unknown');reader=ControlReader();future=Future()
        try:
            with patch.object(reader.pool,'submit',return_value=future) as submit:
                reader.sample(vision,frame,obs,0);submit.assert_not_called()
                reader.sample(vision,frame,obs,.5);submit.assert_called_once()
                future.set_result(Observation('reward',dismiss_point=(200,800)))
                self.assertEqual(reader.sample(vision,frame,obs,.7).state,'reward')
                changed=np.zeros_like(frame)
                self.assertEqual(reader.sample(vision,changed,obs,.9).state,'unknown')
        finally:reader.close()


class RaftingTraceTests(unittest.TestCase):
    def test_failure_trace_is_bounded_and_keeps_the_retry_gate(self):
        import json,tempfile
        from rafting.trace import Trace
        trace=Trace();engine=Engine(Settings());obs=Observation('ready',wheel_pose=tuple([0]*28))
        frame=np.zeros((960,540,3),np.uint8)
        engine.ambiguous_change=True
        for index in range(50):
            trace.add(frame,obs,engine,Action(message='waiting'),index*.5,index*.5)
        self.assertEqual(len(trace.frames),40)
        with tempfile.TemporaryDirectory() as folder,patch('rafting.trace.ROOT',Path(folder)):
            trace.save('test failure')
            result=json.loads((Path(folder)/'logs/rafting-last-trace/trace.json').read_text())
            self.assertEqual(len(result['frames']),40)
            self.assertTrue(result['events'][-1]['ambiguous'])
            self.assertEqual(result['events'][-1]['pose'],[0]*28)


class RaftingVisionTests(unittest.TestCase):
    def test_accept_depends_only_on_green_button_and_label_not_cards(self):
        for name in ('cardpack','cardpack-three'):
            frame=self.fixture(name)
            blank=frame.copy()
            v=Vision();game=v.normalize(frame);_,top,width,_=v.rect
            button=v.bottom_buttons(game)[0]
            blank[top:round(top+button[1]*width/540)-3]=0
            for source in (frame,blank):
                for scale in (.75,1.,1.25):
                    with self.subTest(name=name,blank=source is blank,scale=scale):
                        resized=cv2.resize(source,None,fx=scale,fy=scale)
                        vision=Vision()
                        with patch.object(vision,'read_text',side_effect=AssertionError('No upper-page OCR')):
                            obs=vision.observe(resized,False,False)
                        self.assertEqual(obs.state,'cardpack')
                        self.assertEqual(obs.dialog_label,'开心收下')
                        self.assertGreater(obs.dismiss_point[1],len(resized)*.8)
                        self.assertEqual(Engine(Settings()).step(obs,0).purpose,'cardpack')
        # The same green area without the accepting label is not this page.
        frame=self.fixture('cardpack-three');v=Vision();game=v.normalize(frame)
        x,y,bw,bh=v.bottom_buttons(game)[0];game[y:y+bh,x:x+bw]=(30,190,90)
        self.assertIsNone(v.accept_button(game))

    def test_accept_ocr_fallback_reads_only_button_label(self):
        frame=self.fixture('cardpack-three');vision=Vision();vision.templates['accept']=None
        with patch.object(vision,'read_text',return_value='开心收下') as text:
            obs=vision.observe(frame,True,False)
        self.assertEqual(obs.state,'cardpack')
        roi=text.call_args.args[0]
        self.assertLess(roi.shape[0],70)
        self.assertGreater(roi.shape[1],400)

    def test_synthetic_activity_dialogs_real_ocr_and_startup_binding(self):
        cases=[('rules-synthetic','panel'),('ranking-synthetic','panel'),
               ('purchase-boat-text-synthetic','purchase'),('purchase-boat-art-synthetic','purchase'),
               ('purchase-boat-dark-art-synthetic','purchase'),
               ('reward-button-synthetic','reward_button')]
        for name,state in cases:
            for scale in (.75,1.25):
                with self.subTest(name=name,scale=scale):
                    frame=cv2.resize(self.fixture(name),None,fx=scale,fy=scale)
                    vision=Vision()
                    fast=vision.observe(frame,False,False)
                    if '-dark-' in name:
                        self.assertIn(fast.state,('reward_button','confirm'))
                        self.assertFalse(fast.dialog_checked)
                    else:self.assertEqual(fast.state,'unknown')
                    obs=vision.observe(frame,True,False)
                    self.assertEqual(obs.state,state)
                    if state=='purchase':self.assertIsNone(obs.dismiss_point)
                    elif state=='panel':
                        self.assertAlmostEqual(obs.dismiss_point[0],489*scale,delta=5)
                        self.assertAlmostEqual(obs.dismiss_point[1],124*scale,delta=5)
                    else:self.assertTrue(obs.reward_context)
                    class KnownVision:
                        def observe(self,frame):return obs
                    self.assertEqual(choose_feature_display([(2,frame)],KnownVision,allow_active=True)[0],2)

    def test_unrelated_purchase_and_rules_without_visible_close_do_not_bind(self):
        unrelated=self.fixture('other-purchase-synthetic')
        self.assertEqual(Vision().observe(unrelated,True,False).state,'unknown')
        with self.assertRaises(RuntimeError):
            choose_feature_display([(2,unrelated)],Vision,allow_active=True)
        rules=self.fixture('rules-synthetic');rules[100:147,460:515]=0
        self.assertEqual(Vision().observe(rules,True,False).state,'unknown')
        with self.assertRaises(RuntimeError):
            choose_feature_display([(2,rules)],Vision,allow_active=True)
        # A generic ranking screen cannot establish the target activity.
        v=Vision();game=v.normalize(self.fixture('ranking-synthetic'))
        with patch.object(v,'read_text',return_value='排行榜'):
            self.assertIsNone(v.activity_dialog(game,v.modal_rect(game)))

    def test_actual_large_capsule_batch_prefers_yellow_all_without_reading_counter(self):
        frame=self.fixture('capsule-batch-next-and-all-phone')
        for width in (541,900,1206):
            resized=cv2.resize(frame,(width,round(len(frame)*width/frame.shape[1])))
            vision=Vision()
            with patch.object(vision,'read_text',side_effect=AssertionError('no OCR on fast path')):
                obs=vision.observe(resized,False,False)
            self.assertEqual((obs.state,obs.capsule_label),('capsule_group','开启全部'))
            self.assertGreater(obs.dismiss_point[0],width*.7)
            self.assertGreater(obs.dismiss_point[1],len(resized)*.84)
            self.assertLess(obs.dismiss_point[1],len(resized)*.92)
            self.assertIsNotNone(vision.capsule_button_signature(resized,obs.dismiss_point))
        game=Vision().normalize(frame);game[964:1004,88:193]=0
        obs=Vision().observe(game,False,False)
        self.assertEqual(obs.capsule_label,'开启全部')
        self.assertEqual(choose_feature_display([(2,frame)],Vision,allow_active=True)[0],2)
        engine=Engine(Settings(boat_budget=3,shutdown_on_stop=True))
        action=engine.step(obs,0);engine.acknowledge(action,0)
        self.assertEqual(action.point,obs.dismiss_point)
        self.assertEqual(engine.step(obs,2).kind,'wait')
        engine.step(Observation('transition'),2.5)
        action=engine.step(Observation('confirm',dismiss_point=(270,1023)),4)
        self.assertEqual(action.purpose,'confirm')
        self.assertEqual(engine.used,0)

    def test_large_capsule_batch_green_fallback_never_clicks_unknown_yellow(self):
        frame=self.fixture('capsule-batch-next-and-all-phone')
        vision=Vision();vision.templates['capsule-all']=None
        obs=vision.observe(frame,False,False)
        self.assertEqual((obs.state,obs.capsule_label),('capsule_group','再开一组'))
        self.assertLess(obs.dismiss_point[0],frame.shape[1]*.4)
        game=vision.normalize(frame)
        # Unknown yellow lettering is not a general continuation button.
        game[1004:1045,320:479]=(0,210,255)
        vision.rect=None
        vision.templates['capsule-next']=None
        generic=vision.observe(game,False,False)
        self.assertEqual(generic.state,'reward_button')
        self.assertLess(generic.dismiss_point[0],270)
        engine=Engine(Settings());self.assertEqual(engine.step(generic,0).kind,'wait')
        engine.after_choice=True
        self.assertEqual(engine.step(generic,1).point,generic.dismiss_point)
        game[970:1065,:270]=0
        yellow_only=vision.observe(game,False,False)
        self.assertNotIn(yellow_only.state,('reward_button','capsule_group'))
        self.assertIsNone(yellow_only.dismiss_point)

    def test_actual_capsule_batch_and_trace_frames_ignore_group_counter(self):
        frame=self.fixture('capsule-batch-5-of-10-sdk')
        for width in (541,900):
            resized=cv2.resize(frame,(width,round(len(frame)*width/frame.shape[1])))
            obs=Vision().observe(resized,False)
            self.assertEqual((obs.state,obs.capsule_label),('capsule_group','再开一组'))
            self.assertGreater(obs.dismiss_point[1],len(resized)*.85)
        self.assertEqual(choose_feature_display([(2,frame)],Vision,allow_active=True)[0],2)
        game=Vision().normalize(frame);game[800:832,230:312]=(43,15,29)
        self.assertEqual(Vision().observe(game,False).state,'capsule_group')
        animation=sorted((ROOT/'tests/fixtures/rafting/capsule-animation').glob('*.jpg'));self.assertEqual(len(animation),40)
        for path in animation:
            self.assertEqual(Vision().observe(Vision.read_image(path),False).state,'capsule_group',path.name)

    def test_open_all_label_and_single_unknown_green_button_fallback(self):
        frame=self.fixture('capsule-batch-5-of-10-sdk')
        vision=Vision();vision.templates['capsule-next']=None
        self.assertEqual(vision.observe(frame,False).state,'reward_button')
        with patch.object(vision,'read_text',return_value='开启全部'):
            obs=vision.observe(frame,True)
        self.assertEqual((obs.state,obs.capsule_label),('capsule_group','开启全部'))

    def test_open_all_is_preferred_when_both_reward_buttons_are_present(self):
        game=Vision().normalize(self.fixture('capsule-batch-5-of-10-sdk'))
        game[799:900]=0
        cv2.rectangle(game,(20,823),(250,886),(50,200,100),-1)
        cv2.rectangle(game,(290,823),(520,886),(50,200,240),-1)
        vision=Vision();vision.templates['capsule-next']=None
        # Return the text of the sampled button, independent of OCR call order.
        with patch.object(vision,'read_text',side_effect=lambda roi,**_: '开启全部' if roi[:,:,2].mean()>150 else '再开一组'):
            obs=vision.observe(game,True)
        self.assertEqual(obs.capsule_label,'开启全部')
        self.assertGreater(obs.dismiss_point[0],270)
    def test_sector_pose_ignores_brightness_change_on_a_real_game_frame(self):
        frame=self.fixture('stock-979-sdk');vision=Vision()
        original=vision.observe(frame,False)
        brighter=cv2.add(frame,np.full(frame.shape,8,np.uint8))
        current=vision.observe(brighter,False)
        self.assertEqual(current.state,'ready')
        self.assertEqual(current.wheel_pose,original.wheel_pose)
        self.assertFalse(current.motion)
    def test_control_observation_never_reads_inventory_or_bottom_text(self):
        frame=self.fixture('stock-979-sdk')
        vision=Vision()
        with patch.object(vision,'read_stock',side_effect=AssertionError('inventory blocks control')),patch.object(vision,'read_text',return_value='x1') as text:
            obs=vision.observe(frame,read_inventory=False)
        self.assertEqual((obs.state,obs.multiplier,obs.stock),('ready',1,None))
        self.assertIsNotNone(obs.visual_signature)
        self.assertEqual(text.call_count,1)

    def test_real_wishbox_choice_and_priority_in_both_capture_formats(self):
        for name in ('choice-wishbox-real','choice-wishbox-sdk'):
            frame=self.fixture(name)
            for scale in (.75,1.,1.25):
                resized=cv2.resize(frame,None,fx=scale,fy=scale)
                obs=Vision().observe(resized,False)
                self.assertEqual(obs.state,'choice',(name,scale))
                self.assertEqual([reward for reward,_ in obs.choices],['stars','lunchbox','wishbox'],(name,scale))
                engine=Engine(Settings())
                self.assertEqual(engine.step(obs,0).point,obs.choices[2][1])
                order=[key for key,_ in REWARDS]
                order.insert(0,order.pop(order.index('lunchbox')))
                engine.update({'priority':order})
                self.assertEqual(engine.step(obs,1).point,obs.choices[1][1])
                for _,point in obs.choices:
                    x,y=map(round,point)
                    patch_pixels=resized[max(0,y-10):y+11,max(0,x-15):x+16]
                    hsv=cv2.cvtColor(patch_pixels,cv2.COLOR_BGR2HSV)
                    self.assertGreater(((hsv[:,:,0]>35)&(hsv[:,:,0]<85)&(hsv[:,:,1]>90)).mean(),.2)

    def test_current_979_and_recorded_stock_labels(self):
        frame=self.fixture('stock-979-sdk')
        for width in (541,900):
            obs=Vision().observe(cv2.resize(frame,(width,round(len(frame)*width/frame.shape[1]))))
            self.assertEqual(obs.stock,979,width)
        vision=Vision();labels=self.fixture('stock-recorded-labels')
        for index,value in enumerate((146,136,126,116,115,114,113,704,707)):
            self.assertEqual(vision.read_stock(labels[index*36:(index+1)*36]),value)

    def test_synthetic_stock_quantities_zero_through_one_thousand(self):
        import json
        sprite=self.fixture('stock-digits-synthetic')
        spans=json.loads((ROOT/'assets/fixtures/rafting/stock-digits-synthetic.json').read_text())['spans']
        glyphs=[sprite[:,x:x+width] for x,width in spans]
        vision=Vision()
        for value in range(1001):
            line=np.concatenate([glyphs[int(char)] for char in str(value)],axis=1)
            roi=np.full((36,175,3),(79,60,68),np.uint8)
            x=(175-line.shape[1])//2;roi[8:29,x:x+line.shape[1]]=line
            self.assertEqual(vision.read_stock(roi),value)

    def test_current_native_997_and_repeated_nines_keep_original_glyphs(self):
        frame=self.fixture('stock-997-sdk')
        for width in (541,900):
            vision=Vision()
            resized=cv2.resize(frame,(width,round(len(frame)*width/frame.shape[1])))
            obs=vision.observe(resized)
            self.assertEqual(obs.stock,997,width)
        game=vision.normalize(resized)
        by=(obs.button[1]-vision.rect[1])*540/(vision.rect[2]-vision.rect[0])
        roi=vision.stock_region(game,by)
        mask=cv2.inRange(cv2.cvtColor(roi,cv2.COLOR_BGR2HSV),(0,0,180),(180,60,255))
        _,_,stats,_=cv2.connectedComponentsWithStats(mask)
        digits=sorted([s for s in stats[1:] if s[4]>=15 and s[3]>=8],key=lambda s:s[0])
        first,last=digits[0],digits[-1]
        repeated=roi.copy()
        source=int(first[0])-1;target=int(last[0])-1;span=int(first[2])+3
        # Synthetic quantity made from the real SDK's 9 glyph, preserving
        # colors/outlines. This is not claimed to be a captured 999 frame.
        repeated[:,target:target+span]=roi[:,source:source+span]
        self.assertEqual(vision.read_stock(repeated),999)

    def test_native_four_digit_stock_is_not_truncated(self):
        frame=self.fixture('stock-1000-sdk')
        for width in (541,900):
            vision=Vision()
            resized=cv2.resize(frame,(width,round(len(frame)*width/frame.shape[1])))
            obs=vision.observe(resized)
            self.assertEqual(obs.state,'ready')
            self.assertEqual(obs.stock,1000,width)
            self.assertEqual(obs.multiplier,1)
            self.assertFalse(obs.free)
            if width==900:
                from rafting.runner import number_samples,same_number_samples
                original=number_samples(vision,resized,obs)
                changed=resized.copy();scale=width/540
                # Only erase the leading digit left of the old x=262 crop.
                changed[int(obs.button[1]+70*scale):int(obs.button[1]+91*scale),int(254*scale):int(262*scale)]=0
                # Inventory no longer invalidates the essential control OCR.
                self.assertTrue(same_number_samples(original,number_samples(vision,changed,obs)))

    def test_single_digit_stock_and_mismatched_ocr_are_checked(self):
        vision=Vision();frame=self.fixture('stock-1000-sdk')
        obs=vision.observe(frame);game=vision.normalize(frame)
        by=(obs.button[1]-vision.rect[1])*540/(vision.rect[2]-vision.rect[0])
        roi=vision.stock_region(game,by)
        with patch.object(vision,'recognize_digits',return_value='0'):
            self.assertIsNone(vision.read_stock(roi))
        with patch.object(vision,'recognize_digits',return_value='10000'):
            self.assertIsNone(vision.read_stock(roi))
        mask=cv2.inRange(cv2.cvtColor(roi,cv2.COLOR_BGR2HSV),(0,0,180),(180,60,255))
        _,_,stats,_=cv2.connectedComponentsWithStats(mask)
        digits=sorted([s for s in stats[1:] if s[4]>=15 and s[3]>=8],key=lambda s:s[0])
        for value,index in ((1,0),(0,3)):
            x,y,w,h,_=map(int,digits[index])
            single=np.zeros_like(roi)
            single[y-3:y+h+3,77:80+w+3]=roi[y-3:y+h+3,x-3:x+w+3]
            self.assertEqual(vision.read_stock(single),value)

    def test_free_on_central_button_with_normal_stock(self):
        vision=Vision()
        frame=vision.read_image(ROOT/'assets/fixtures/rafting/free-spin-user.png')
        for width in (541,900):
            vision=Vision()
            resized=cv2.resize(frame,(width,round(frame.shape[0]*width/frame.shape[1])))
            obs=vision.observe(resized)
            self.assertEqual(obs.state,'ready')
            self.assertEqual(obs.stock,512)
            self.assertTrue(obs.free)
            self.assertEqual(obs.multiplier,1)
            self.assertTrue(obs.numbers_fresh)
        paid=vision.observe(self.fixture('ready'))
        self.assertFalse(paid.free)

    def fixture(self, name):
        return Vision.read_image(ROOT/'assets/fixtures/rafting'/f'{name}.png')

    def test_user_screenshots_read_multiplier_stock_and_max(self):
        for name, value, maximum in [('ready', 1, False), ('x3', 3, False), ('maximum', 10, True)]:
            vision = Vision()
            obs = vision.observe(self.fixture(name))
            self.assertEqual(obs.state, 'ready')
            self.assertEqual(obs.multiplier, value)
            self.assertEqual(obs.stock, 50)
            self.assertEqual(obs.maximum, maximum)
            self.assertAlmostEqual(obs.button[0], 274, delta=5)
            self.assertAlmostEqual(obs.button[1], 834, delta=5)

    def test_gray_multiplier_from_user_video(self):
        vision=Vision()
        frame=vision.read_image(ROOT/'assets/fixtures/rafting/gray-x1.jpg')
        obs=vision.observe(frame)
        self.assertEqual(obs.multiplier,1)
        self.assertEqual(obs.stock,116)

    def test_sdk_idle_avatars_do_not_restart_settlement(self):
        vision=Vision()
        first=self.fixture('idle-avatars-a');second=self.fixture('idle-avatars-b')
        a=vision.observe(first,False);b=vision.observe(second,False)
        self.assertEqual((a.state,b.state),('ready','ready'))
        self.assertFalse(b.motion)
        engine=Engine(Settings())
        engine.takeover(0)
        engine.step(a,7);engine.step(b,9.1)
        self.assertEqual(engine.completed,1)
        self.assertFalse(engine.active_round)

    def test_hull_horizontal_movement_ignores_small_and_vertical_bobbing(self):
        vision=Vision()
        def boat(x,y):
            game=np.zeros((960,540,3),np.uint8)
            cv2.rectangle(game,(x,y),(x+170,y+85),(50,220,130),-1)
            return game
        self.assertFalse(vision.boat_motion(boat(180,420)))
        self.assertFalse(vision.boat_motion(boat(182,432)))
        self.assertFalse(vision.boat_motion(boat(178,415)))
        self.assertFalse(vision.boat_motion(boat(189,430)))
        self.assertFalse(vision.boat_motion(boat(171,412)))
        self.assertFalse(vision.boat_motion(boat(189,420)))
        self.assertTrue(vision.boat_motion(boat(205,420)))
        self.assertFalse(vision.boat_motion(boat(205,420)))
        self.assertIsNone(vision.boat_motion(np.zeros((960,540,3),np.uint8)))

    def test_three_digit_multiplier_text_and_unsupported_values(self):
        for text,value in [('x2',2),('×100',100),('X 150',150),('x15',None),('x151',None),('150米',None)]:
            vision=Vision()
            with patch.object(vision,'read_text',return_value=text):
                obs=vision.observe(self.fixture('ready'))
            self.assertEqual(obs.multiplier,value,text)

    def test_both_choice_screens_and_distracting_header(self):
        for name, rewards in [('choice6', ['raft', 'coins', 'capsule']), ('choice7', ['coins', 'stars', 'capsule'])]:
            image = self.fixture(name)
            image[:30] = np.random.default_rng(42).integers(0, 256, image[:30].shape, np.uint8)
            choices = Vision().reward_choices(image, partial=True)
            self.assertEqual([r for r, _ in choices], rewards)
            for _, point in choices:
                self.assertGreater(point[1], 160)

    def test_center_dialog_in_full_game_and_resizing(self):
        image = self.fixture('ready')
        popup = self.fixture('choice7')
        for scale in (.75, 1., 1.25):
            full = image.copy()
            full[350:350+popup.shape[0], 80:80+popup.shape[1]] = popup
            full = cv2.resize(full, None, fx=scale, fy=scale)
            obs = Vision().observe(full, read_numbers=False)
            self.assertEqual(obs.state, 'choice')
            self.assertEqual([r for r, _ in obs.choices], ['coins', 'stars', 'capsule'])
            self.assertAlmostEqual(obs.choices[0][1][0], 134.5*scale, delta=5)

    def test_all_six_samples_and_unknown_card(self):
        vision = Vision()
        for key, template in vision.rewards.items():
            roi = cv2.copyMakeBorder(template, 8, 8, 8, 8, cv2.BORDER_CONSTANT)
            self.assertEqual(vision.classify_reward(roi), key)
        self.assertIsNone(vision.classify_reward(np.zeros((100, 100, 3), np.uint8)))

    def test_feature_display_binding_checks_uniqueness(self):
        frame = self.fixture('ready')
        binding = choose_feature_display([(0, None), (2, frame)], Vision)
        self.assertEqual(binding, (2, 547, 1010, 1))
        with self.assertRaises(RuntimeError):
            choose_feature_display([(1, frame), (2, frame)], Vision)

    def test_recorded_reward_flow_and_takeover_binding(self):
        for name,state in [('cardpack','cardpack'),('reward-full','reward'),('confirm-full','confirm'),('choice-full','choice'),('choice-lunch','choice'),('choice-boat','choice'),('choice-wishbox-synthetic','choice')]:
            frame=self.fixture(name)
            for scale in (.75,1,1.25):
                resized=cv2.resize(frame,None,fx=scale,fy=scale)
                obs=Vision().observe(resized,False)
                self.assertEqual(obs.state,state,(name,scale,obs))
                if state=='choice':self.assertTrue(all(r for r,_ in obs.choices),(name,obs))
                else:self.assertGreater(obs.dismiss_point[1],frame.shape[0]*scale*.7)
            binding=choose_feature_display([(2,frame)],Vision,allow_active=True)
            self.assertEqual(binding[0],2)
        obs=Vision().observe(self.fixture('choice-wishbox-synthetic'),False)
        self.assertEqual(obs.choices[0][0],'wishbox')


class RaftingShutdownTests(unittest.TestCase):
    def backend(self):
        from PySide6.QtCore import QCoreApplication
        from rafting.backend import RaftingBackend
        self.app=QCoreApplication.instance() or QCoreApplication([])
        backend=RaftingBackend(discover=False);backend.timer.stop();backend.persist=lambda:None
        return backend

    def test_normal_stop_countdown_cancellation_and_dispatch(self):
        b=self.backend();b.setValue('shutdown_on_stop',True)
        with patch('fishing.shutdown.request_shutdown') as shutdown:
            b.update(running=True,normalStop=True);b.poll()
            self.assertTrue(b.state['shutdownPending']);shutdown.assert_not_called()
            b.cancelShutdown();self.assertFalse(b.state['shutdownPending'])
            b.update(running=True,normalStop=True);b.poll();b.shutdown_deadline=time.monotonic()-1;b.poll()
            shutdown.assert_called_once_with(False)

    def test_errors_manual_close_and_restart_do_not_shutdown(self):
        for manual,closing,normal in [(True,False,True),(False,True,True),(False,False,False)]:
            b=self.backend();b.setValue('shutdown_on_stop',True)
            b.manual_stop=manual;b.closing=closing;b.update(running=True,normalStop=normal);b.poll()
            self.assertFalse(b.state['shutdownPending'])
        self.assertFalse(self.backend().state['shutdown_on_stop'])

    def test_force_shutdown_uses_same_countdown_and_can_be_cancelled(self):
        b=self.backend();b.setValue('shutdown_force',True)
        b.update(running=True,normalStop=True);b.poll()
        self.assertFalse(b.state['shutdownPending'])
        b.setValue('shutdown_on_stop',True)
        with patch('fishing.shutdown.request_shutdown') as shutdown:
            b.update(running=True,normalStop=True);b.poll()
            self.assertTrue(b.state['shutdownPending'])
            b.setValue('shutdown_on_stop',False)
            self.assertFalse(b.state['shutdownPending']);shutdown.assert_not_called()
            b.setValue('shutdown_on_stop',True)
            b.update(running=True,normalStop=True);b.poll();b.shutdown_deadline=time.monotonic()-1;b.poll()
            shutdown.assert_called_once_with(True)


class RaftingRunnerTests(unittest.TestCase):
    def test_purchase_dialog_stops_runner_without_sending_any_input(self):
        from rafting.runner import run
        vision=Vision();frame=vision.read_image(ROOT/'assets/fixtures/rafting/purchase-boat-art-synthetic.png')
        purchase=vision.observe(frame,True,False)
        self.controls.sample.side_effect=lambda vision,frame,obs,now:purchase
        cancel=threading.Event();capture=MagicMock();mouse=MagicMock();mouse.size=(540,len(frame))
        clock={'now':0.}
        def read():
            clock['now']+=.5
            return frame,clock['now'],clock['now'],mouse.size
        capture.read.side_effect=read;messages=[]
        with patch('rafting.runner.connect',return_value=(capture,mouse)),patch('rafting.runner.Vision',return_value=vision),patch('rafting.runner.time.monotonic',side_effect=lambda:clock['now']),patch('rafting.runner.user32.GetAsyncKeyState',return_value=0),patch('rafting.runner.recovery_snapshot'):
            run(None,Settings(shutdown_on_stop=True),cancel,messages.append,queue.Queue())
        mouse.click.assert_not_called()
        self.assertEqual(messages[-1]['used'],0)
        self.assertFalse(messages[-1]['normalStop'])

    def setUp(self):
        control_patch=patch('rafting.runner.ControlReader')
        self.controls=control_patch.start().return_value
        self.controls.sample.side_effect=lambda vision,frame,obs,now:obs
        self.addCleanup(control_patch.stop)
        trace_patch=patch('rafting.runner.Trace')
        trace_patch.start();self.addCleanup(trace_patch.stop)

    def test_actual_capsule_result_clicks_bottom_button_without_boat_budget(self):
        from rafting.runner import run
        for name in ('capsule-batch-5-of-10-sdk','capsule-batch-next-and-all-phone'):
            with self.subTest(fixture=name):
                vision=Vision();frame=vision.read_image(ROOT/f'assets/fixtures/rafting/{name}.png')
                expected=vision.observe(frame,False).dismiss_point
                cancel=threading.Event();capture=MagicMock();mouse=MagicMock();mouse.size=(frame.shape[1],len(frame))
                clock={'now':0.}
                def read():
                    clock['now']+=.5
                    return frame,clock['now'],clock['now'],mouse.size
                capture.read.side_effect=read;mouse.click.side_effect=lambda point:cancel.set()
                messages=[]
                with patch('rafting.runner.connect',return_value=(capture,mouse)),patch('rafting.runner.Vision',return_value=vision),patch('rafting.runner.time.monotonic',side_effect=lambda:clock['now']),patch('rafting.runner.user32.GetAsyncKeyState',return_value=0):
                    run(None,Settings(),cancel,messages.append,queue.Queue())
                mouse.click.assert_called_once_with(expected)
                self.assertGreater(expected[1],len(frame)*.84)
                self.assertEqual(messages[-1]['used'],0)

    def test_actual_accept_page_retries_real_input_path_without_spending_boats(self):
        from rafting.runner import run
        vision=Vision();frame=vision.read_image(ROOT/'assets/fixtures/rafting/cardpack-three.png')
        expected=vision.observe(frame,False,False).dismiss_point
        cancel=threading.Event();capture=MagicMock();mouse=MagicMock();mouse.size=(frame.shape[1],len(frame))
        clock={'now':0.}
        def read():
            clock['now']+=.5
            return frame,clock['now'],clock['now'],mouse.size
        capture.read.side_effect=read;messages=[]
        with patch('rafting.runner.connect',return_value=(capture,mouse)),patch('rafting.runner.Vision',return_value=vision),patch('rafting.runner.time.monotonic',side_effect=lambda:clock['now']),patch('rafting.runner.user32.GetAsyncKeyState',return_value=0),patch('rafting.runner.recovery_snapshot'):
            run(None,Settings(shutdown_on_stop=True),cancel,messages.append,queue.Queue())
        self.assertEqual(mouse.click.call_count,3)
        for call in mouse.click.call_args_list:self.assertEqual(call.args,(expected,))
        self.assertEqual(messages[-1]['used'],0)
        self.assertFalse(messages[-1]['normalStop'])

    def test_other_reward_pages_reconfirm_and_really_retry_input_without_budget(self):
        from rafting.runner import run
        for name in ('confirm-full','choice-full','reward-button-synthetic','capsule-batch-5-of-10-sdk'):
            with self.subTest(fixture=name):
                vision=Vision();frame=vision.read_image(ROOT/f'assets/fixtures/rafting/{name}.png')
                known=vision.observe(frame,True,False);expected=Engine(Settings()).step(known,0).point
                self.assertIsNotNone(expected)
                self.controls.sample.side_effect=lambda vision,frame,obs,now:known
                cancel=threading.Event();capture=MagicMock();mouse=MagicMock();mouse.size=(frame.shape[1],len(frame))
                clock={'now':0.}
                def read():
                    clock['now']+=.5
                    return frame,clock['now'],clock['now'],mouse.size
                capture.read.side_effect=read;messages=[]
                with patch('rafting.runner.connect',return_value=(capture,mouse)),patch('rafting.runner.Vision',return_value=vision),patch('rafting.runner.time.monotonic',side_effect=lambda:clock['now']),patch('rafting.runner.user32.GetAsyncKeyState',return_value=0),patch('rafting.runner.recovery_snapshot'):
                    run(None,Settings(shutdown_on_stop=True),cancel,messages.append,queue.Queue())
                self.assertEqual(mouse.click.call_count,3)
                for call in mouse.click.call_args_list:self.assertEqual(call.args,(expected,))
                self.assertEqual(messages[-1]['used'],0)
                self.assertFalse(messages[-1]['normalStop'])

    def test_unresponsive_spin_retries_really_click_the_boat_button_three_times(self):
        from rafting.runner import run
        cancel=threading.Event();capture=MagicMock();mouse=MagicMock();mouse.size=(492,912)
        clock={'now':0.}
        def read():
            clock['now']+=.5
            return np.zeros((912,492,3),np.uint8),clock['now'],clock['now'],mouse.size
        capture.read.side_effect=read
        messages=[]
        with patch('rafting.runner.connect',return_value=(capture,mouse)),patch('rafting.runner.Vision') as vision,patch('rafting.runner.InventoryReader') as inventory,patch('rafting.runner.time.monotonic',side_effect=lambda:clock['now']),patch('rafting.runner.user32.GetAsyncKeyState',return_value=0),patch('rafting.runner.recovery_snapshot'):
            vision.return_value.observe.return_value=Observation('ready',(270,800),multiplier=3,
                            visual_signature=b'frame',wheel_pose=tuple([0,1]*14))
            inventory.return_value.sample.return_value=None
            run(None,Settings(desired_multiplier=3,boat_budget=3),cancel,messages.append,queue.Queue())
        self.assertEqual(mouse.click.call_count,3)
        self.assertEqual([call.args[0] for call in mouse.click.call_args_list],[(270,800)]*3)
        self.assertEqual(messages[-1]['used'],3)
        self.assertEqual(messages[-1]['rounds'],0)
        self.assertFalse(messages[-1]['normalStop'])
    def test_inventory_reference_zero_does_not_block_a_fresh_spin(self):
        from rafting.runner import run
        cancel=threading.Event();capture=MagicMock();mouse=MagicMock();mouse.size=(492,912)
        clock={'now':0.}
        def read():
            clock['now']+=.4
            return np.zeros((912,492,3),np.uint8),clock['now'],clock['now'],mouse.size
        capture.read.side_effect=read
        mouse.click.side_effect=lambda point:cancel.set()
        messages=[]
        with patch('rafting.runner.connect',return_value=(capture,mouse)),patch('rafting.runner.Vision') as vision,patch('rafting.runner.InventoryReader') as inventory,patch('rafting.runner.time.monotonic',side_effect=lambda:clock['now']),patch('rafting.runner.user32.GetAsyncKeyState',return_value=0),patch('rafting.runner.number_samples',return_value=None):
            vision.return_value.observe.return_value=Observation('ready',(270,800),multiplier=3,stock=None,visual_signature=b'frame')
            inventory.return_value.sample.return_value=0
            run(None,Settings(desired_multiplier=3),cancel,messages.append,queue.Queue())
            for call in vision.return_value.observe.call_args_list:
                self.assertFalse(call.kwargs['read_inventory'])
            inventory.return_value.close.assert_called_once()
        mouse.click.assert_called_once_with((270,800))
        self.assertFalse(messages[-1]['normalStop'])

    def test_capture_recovery_has_three_windows_and_resets(self):
        from rafting.runner import FrameRecovery
        recovery=FrameRecovery()
        for now,expected in [(10,(1,False)),(12.9,(1,False)),(13,(2,False)),(16,(3,False)),(19,(3,True))]:
            self.assertEqual(recovery.check(now),expected)
        recovery.reset()
        self.assertEqual(recovery.check(30),(1,False))

    def test_stale_frames_recover_without_input_or_restart(self):
        from rafting.runner import run
        cancel=threading.Event();capture=MagicMock();mouse=MagicMock();mouse.size=(492,912)
        clock={'now':10.};sequence={'value':0}
        def read():
            sequence['value']+=1
            if sequence['value']<3:
                clock['now']+=3
                return np.zeros((912,492,3),np.uint8),clock['now']-2,sequence['value'],mouse.size
            return np.zeros((912,492,3),np.uint8),clock['now'],sequence['value'],mouse.size
        capture.read.side_effect=read
        messages=[]
        def publish(value):
            messages.append(value)
            if value.get('phase')=='ready':cancel.set()
        with patch('rafting.runner.connect',return_value=(capture,mouse)),patch('rafting.runner.Vision') as vision,patch('rafting.runner.time.monotonic',side_effect=lambda:clock['now']),patch('rafting.runner.user32.GetAsyncKeyState',return_value=0):
            vision.return_value.observe.return_value=Observation('ready')
            run(None,Settings(),cancel,publish,queue.Queue())
        self.assertTrue(any('1/3' in v.get('status','') for v in messages))
        self.assertTrue(any('2/3' in v.get('status','') for v in messages))
        self.assertTrue(any(v.get('phase')=='ready' for v in messages))
        mouse.click.assert_not_called()

    def test_capture_failure_stops_after_three_windows_without_input(self):
        from rafting.runner import run
        cancel=threading.Event();capture=MagicMock();mouse=MagicMock();mouse.size=(492,912)
        clock={'now':0.}
        def read():clock['now']+=3;return None
        capture.read.side_effect=read
        messages=[]
        with patch('rafting.runner.connect',return_value=(capture,mouse)),patch('rafting.runner.time.monotonic',side_effect=lambda:clock['now']),patch('rafting.runner.user32.GetAsyncKeyState',return_value=0),patch('rafting.runner.recovery_snapshot') as snapshot:
            run(None,Settings(),cancel,messages.append,queue.Queue())
        self.assertEqual(capture.read.call_count,4)
        self.assertTrue(any('3/3' in v.get('status','') for v in messages))
        self.assertTrue(any('画面仍未更新' in v.get('status','') for v in messages))
        mouse.click.assert_not_called();snapshot.assert_called_once()

    def test_capture_gap_recovers_but_blocks_ambiguous_spin_retry(self):
        from rafting.runner import run
        cancel=threading.Event();capture=MagicMock();mouse=MagicMock();mouse.size=(492,912)
        clock={'now':1.};sequence={'value':0}
        engine=Engine(Settings(desired_multiplier=3))
        engine.acknowledge(Action(purpose='spin'),1,3,stock=50)
        def read():
            sequence['value']+=1;clock['now']+=3
            if sequence['value']==1:raise RuntimeError('截图暂时失败')
            return np.zeros((912,492,3),np.uint8),clock['now'],sequence['value'],mouse.size
        capture.read.side_effect=read
        messages=[]
        with patch('rafting.runner.connect',return_value=(capture,mouse)),patch('rafting.runner.Vision') as vision,patch('rafting.runner.Engine',return_value=engine),patch('rafting.runner.number_samples',return_value=None),patch('rafting.runner.time.monotonic',side_effect=lambda:clock['now']),patch('rafting.runner.user32.GetAsyncKeyState',return_value=0),patch('rafting.runner.recovery_snapshot'):
            vision.return_value.observe.return_value=Observation('ready',multiplier=3,stock=50,numbers_fresh=True)
            run(None,Settings(),cancel,messages.append,queue.Queue())
        self.assertTrue(engine.ambiguous_change)
        self.assertTrue(any('重新获取' in v.get('status','') for v in messages))
        self.assertTrue(any('重新检查' in v.get('status','') for v in messages))
        self.assertTrue(any('启动转盘未确认' in v.get('status','') for v in messages))
        self.assertEqual(engine.used,3)
        self.assertFalse(messages[-1]['normalStop'])
        mouse.click.assert_not_called()

    def test_ready_ocr_cache_ignores_avatars_and_inventory_but_detects_free(self):
        from rafting.runner import number_samples, same_number_samples
        vision=Vision()
        frame=vision.read_image(ROOT/'assets/fixtures/rafting/free-spin-user.png')
        obs=vision.observe(frame)
        original=number_samples(vision,frame,obs)
        avatars=frame.copy();avatars[200:570,:]=0
        self.assertTrue(same_number_samples(original,number_samples(vision,avatars,obs)))
        free=frame.copy();free[840:869,238:300]=0
        self.assertFalse(same_number_samples(original,number_samples(vision,free,obs)))
        stock=frame.copy();stock[902:927,262:326]=0
        self.assertTrue(same_number_samples(original,number_samples(vision,stock,obs)))

    def test_slow_ocr_with_moving_avatars_reaches_fresh_free_spin(self):
        from rafting.runner import run
        vision=Vision();frame=vision.read_image(ROOT/'assets/fixtures/rafting/free-spin-user.png')
        initial=vision.observe(frame)
        cancel=threading.Event();capture=MagicMock();mouse=MagicMock();mouse.size=(frame.shape[1],frame.shape[0])
        clock={'now':0.};sequence={'value':0};read_flags=[]
        def read():
            sequence['value']+=1
            clock['now']+=.2
            current=frame.copy();current[200:570,:]=sequence['value']*25
            return current,clock['now'],sequence['value'],mouse.size
        capture.read.side_effect=read
        def observe(current,read_numbers=True,read_inventory=True):
            self.assertFalse(read_inventory)
            read_flags.append(read_numbers)
            self.assertFalse(read_numbers)
            return replace(initial,multiplier=None,stock=None,numbers_fresh=False)
        vision.observe=observe
        self.controls.sample.side_effect=lambda vision,frame,obs,now:replace(obs,multiplier=initial.multiplier)
        mouse.click.side_effect=lambda point:cancel.set()
        messages=[]
        with patch('rafting.runner.connect',return_value=(capture,mouse)),patch('rafting.runner.Vision',return_value=vision),patch('rafting.runner.time.monotonic',side_effect=lambda:clock['now']),patch('rafting.runner.user32.GetAsyncKeyState',return_value=0):
            run(None,Settings(desired_multiplier=1),cancel,messages.append,queue.Queue())
        self.assertEqual(read_flags,[False,False,False])
        mouse.click.assert_called_once_with(initial.button)
        self.assertEqual(messages[-1]['used'],0)
        self.assertTrue(any(m.get('status')=='设备已连接，正在识别漂流画面…' for m in messages))

    def test_slow_ocr_keeps_progress_but_never_clicks_old_frame(self):
        from rafting.runner import run
        cancel=threading.Event();capture=MagicMock();mouse=MagicMock();mouse.size=(492,912)
        clock={'now':9.};times=iter([10.,15.,16.])
        engine=Engine(Settings(desired_multiplier=3))
        engine.acknowledge(Action(purpose='spin'),9,3,stock=50)
        def read():
            clock['now']=next(times)
            return np.zeros((912,492,3),np.uint8),clock['now'],clock['now'],mouse.size
        capture.read.side_effect=read
        observations=iter([Observation('ready',motion=True),Observation('ready'),Observation('ready')])
        def observe(*args,**kwargs):
            obs=next(observations)
            if obs.motion:clock['now']+=1.1
            return obs
        messages=[]
        def publish(value):
            messages.append(value)
            if value.get('rounds')==1:cancel.set()
        with patch('rafting.runner.connect',return_value=(capture,mouse)),patch('rafting.runner.Vision') as vision,patch('rafting.runner.Engine',return_value=engine),patch('rafting.runner.time.monotonic',side_effect=lambda:clock['now']),patch('rafting.runner.user32.GetAsyncKeyState',return_value=0):
            vision.return_value.observe.side_effect=observe
            run(None,Settings(),cancel,publish,queue.Queue())
        self.assertEqual(engine.completed,1)
        mouse.click.assert_not_called()
        self.assertFalse(messages[-1]['normalStop'])
        mouse.close.assert_called_once();capture.close.assert_called_once()

    def test_normal_completion_requires_successful_cleanup_and_no_cancel(self):
        from rafting.runner import run
        from rafting.engine import Action
        for cleanup_error,cancel_during,expected in [(False,False,True),(True,False,False),(False,True,False)]:
            cancel=threading.Event();capture=MagicMock();mouse=MagicMock();mouse.size=(492,912)
            capture.read.return_value=(np.zeros((912,492,3),np.uint8),10,1,mouse.size)
            if cleanup_error:mouse.close.side_effect=OSError('release failed')
            messages=[]
            with patch('rafting.runner.connect',return_value=(capture,mouse)),patch('rafting.runner.Vision') as vision,patch('rafting.runner.Engine') as factory,patch('rafting.runner.time.monotonic',return_value=10),patch('rafting.runner.user32.GetAsyncKeyState',return_value=0):
                engine=factory.return_value;engine.completed=1;engine.used=3
                vision.return_value.observe.return_value=Observation('ready',multiplier=3,stock=50)
                def stop(obs,now):
                    if cancel_during:cancel.set()
                    return Action('stop',purpose='auto_stop')
                engine.step.side_effect=stop
                run(None,Settings(),cancel,messages.append,queue.Queue())
            self.assertEqual(messages[-1]['normalStop'],expected)
            mouse.close.assert_called_once();capture.close.assert_called_once()


class RaftingUiTests(QtUiCase):
    def test_narrow_page_all_tiers_budget_and_force_shutdown(self):
        self.run_qt('''
from PySide6.QtTest import QTest
from PySide6.QtCore import QObject,QPointF,Qt
from autotata.app import Shell
s=Shell(discover=False,animations=False);s.nav.openRafting();QTest.qWait(150)
b=s.nav.rafting;b.persist=lambda:None
assert s.window.property('baseWidth')==615
assert b.state['multipliers']==[1,2,3,5,10,20,50,100,150]
def items(item):
 yield item
 for child in item.childItems():yield from items(child)
buttons=[item for item in items(s.window.contentItem()) if item.objectName().startswith('raftingMultiplier')]
assert len(buttons)==9,[(x.objectName(),x.property('text')) for x in buttons]
for value,item in zip(b.state['multipliers'],buttons):
 point=item.mapToScene(QPointF(item.width()/2,item.height()/2)).toPoint()
 assert 0<point.x()<s.window.width(),(value,point)
 QTest.mouseClick(s.window,Qt.LeftButton,Qt.NoModifier,point);QTest.qWait(15)
 assert b.state['desired_multiplier']==value,(value,b.state)
budget=s.window.findChild(QObject,'raftingBudget')
assert budget is not None
force=s.window.findChild(QObject,'raftingForceShutdown')
assert force is not None
QTest.mouseClick(s.window,Qt.LeftButton,Qt.NoModifier,force.mapToScene(QPointF(40,14)).toPoint())
assert b.state['shutdown_force']
assert not b.state['shutdown_on_stop']
assert not s.errors,s.errors
b.close();b.timer.stop()
''')

    def test_feature_startup_uses_each_feature_icon(self):
        self.run_qt('''
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtCore import QUrl,QObject
from autotata.paths import ASSETS
app=QGuiApplication([])
for kind,name in [('fishing','rod-wood.png'),('rafting','rafting.png'),('treasure','treasure.png')]:
 e=QQmlApplicationEngine();e.rootContext().setContextProperty('assetBase',QUrl.fromLocalFile(str(ASSETS.resolve())+'/').toString());e.rootContext().setContextProperty('featureKind',kind)
 e.load(QUrl.fromLocalFile(str(ASSETS/'ui/FeatureStartup.qml')))
 root=e.rootObjects()[0];icon=root.findChild(QObject,'featureStartupIcon')
 assert icon.property('source').toString().endswith(name),kind
 root.close()
e=QQmlApplicationEngine();e.rootContext().setContextProperty('assetBase',QUrl.fromLocalFile(str(ASSETS.resolve())+'/').toString());e.load(QUrl.fromLocalFile(str(ASSETS/'ui/Startup.qml')))
root=e.rootObjects()[0];root.setProperty('iconSource',QUrl.fromLocalFile(str(ASSETS/'ui/rod-wood.png')).toString())
assert root.findChild(QObject,'startupIcon').property('source').toString().endswith('rod-wood.png')
root.close()
from fishing.gpu_app import GpuApp
fish=GpuApp(discover=False,hotkeys=False)
assert fish.window.findChild(QObject,'startButton').property('iconSource').toString().endswith('rod-wood.png')
fish.backend.timer.stop()
''')

    def test_actual_drag_changes_priority(self):
        self.run_qt('''
from PySide6.QtTest import QTest
from PySide6.QtCore import QObject,QPointF,Qt
from autotata.app import Shell
s=Shell(discover=False,animations=False);s.nav.openRafting();QTest.qWait(150)
b=s.nav.rafting;b.persist=lambda:None
def find(item):
 if item.objectName()=='rewardDrag0':return item
 for child in item.childItems():
  found=find(child)
  if found:return found
item=find(s.window.contentItem())
start=item.mapToScene(QPointF(40,45)).toPoint()
# mapToScene returns window coordinates, including the fitted scene scale.
end=item.mapToScene(QPointF(238,45)).toPoint()
QTest.mousePress(s.window,Qt.LeftButton,Qt.NoModifier,start)
for i in range(1,8):
 QTest.mouseMove(s.window,start+(end-start)*i/7,20)
QTest.mouseRelease(s.window,Qt.LeftButton,Qt.NoModifier,end)
QTest.qWait(100)
assert b.state['rewards'][2]['key']=='wishbox',b.state['rewards']
b.restoreRecommended()
assert b.state['rewards'][0]['key']=='wishbox'
b.setValue('boat_budget',17)
assert b.state['boat_budget']==17
b.setValue('boat_budget',-1)
assert b.state['boat_budget']==17
assert not b.state['shutdown_on_stop']
assert not s.errors,s.errors
b.close();b.timer.stop()
''')

    def test_navigation_order_and_lazy_loading(self):
        self.run_qt('''
import sys
from PySide6.QtTest import QTest
from autotata.app import Shell
s=Shell(discover=False,animations=False)
assert 'rafting' not in sys.modules
assert not s.window.property('raftingLoaded')
s.nav.openRafting();QTest.qWait(100)
b=s.nav.rafting;b.persist=lambda:None
assert s.window.property('page')=='rafting'
assert s.nav.fishing is None and s.nav.treasure is None
assert len(b.state['rewards'])==6
b.moveReward(0,5)
assert b.state['rewards'][-1]['key']=='wishbox'
b.setValue('desired_multiplier',20)
assert b.state['desired_multiplier']==20
b.update(running=True)
s.nav.returnHome();assert s.window.property('page')=='rafting'
b.update(running=False);s.nav.returnHome()
assert s.window.property('page')=='home'
b.setValue('boat_budget',17)
assert b.state['boat_budget']==17
b.setValue('boat_budget',-1)
assert b.state['boat_budget']==17
assert not b.state['shutdown_on_stop']
assert not s.errors,s.errors
b.close();b.timer.stop()
''')


if __name__ == '__main__':
    unittest.main()
