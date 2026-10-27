import unittest
from fishing.bait import BaitMaintenance
from fishing.engine import Engine,Settings,Action
from fishing.vision import Observation


def obs(t, luck=4, level=1, stock=10, state='ready', motion=False, cap=False):
    return Observation(state,(270,800),(360,750),(480,760),(270,500),
        multiplier=1,bait_available=stock!=0,bait_confirm_point=(430,600),
        rod_level=level,luck=luck,bait_stock=stock,bait_motion=motion,
        bait_capped=cap,bait_sample_at=t)


class BaitMaintenanceTests(unittest.TestCase):
    def make(self, **kw):
        b=BaitMaintenance(Settings(auto_bait=True,desired_multiplier=1,**kw),delay=lambda:2.)
        return b
    def tick(self,b,t,**kw):
        o=obs(t,**kw);b.observe(o,t)
        return b.action(o,t,Action,ready=o.state=='ready')
    def stable(self,b,t=0,**kw):
        for dt in (0,.4,.8):a=self.tick(b,t+dt,**kw)
        return a
    def opening(self,b):
        self.stable(b)
        self.stable(b,17)
        a=self.tick(b,18.2)
        self.assertEqual(b.phase,'opening')
        return a
    def submitted(self,b):
        self.opening(b)
        a=self.tick(b,18.6,state='bait_menu')
        self.assertEqual(a.purpose,'bait_confirm')
        b.submitted(18.7)

    def test_runtime_disable_cancels_unsubmitted_bait(self):
        b=self.make();self.opening(b);b.settings.auto_bait=False
        self.assertEqual(self.tick(b,18.6,state='bait_menu').purpose,'bait_cancel')
        self.assertEqual(b.used,0)

    def test_runtime_disable_keeps_submitted_outcome_gate(self):
        b=self.make();self.submitted(b);b.settings.auto_bait=False
        self.assertEqual(self.tick(b,19,motion=True).kind,'wait')
        self.assertEqual(b.phase,'verifying')

    def test_all_four_grade_targets(self):
        for level in range(1,5):
            b=self.make();self.stable(b,level=level,luck=level+4)
            self.assertEqual(b.target,level+4);self.assertIsNone(b.deadline)
    def test_wait_has_fixed_deadline_not_reset_every_frame(self):
        b=self.make();self.stable(b)
        deadline=b.deadline
        for t in (1.2,2,4,6,10):self.tick(b,t)
        self.assertEqual(b.deadline,deadline)
        self.stable(b,17)
        self.assertEqual(b.phase,'opening')
    def test_team_fill_cancels_wait_without_spending(self):
        b=self.make();self.stable(b);self.stable(b,2,luck=5)
        self.assertIsNone(b.deadline);self.assertIsNone(b.phase);self.assertEqual(b.used,0)
    def test_team_partial_increase_rearms_only_once(self):
        b=self.make();self.stable(b,luck=2);self.stable(b,2,luck=3)
        deadline=b.deadline
        self.tick(b,4,luck=3);self.assertEqual(b.deadline,deadline)
    def test_no_count_on_click_or_luck_increase(self):
        b=self.make();self.submitted(b);self.assertEqual(b.used,0)
        self.stable(b,20,luck=5,stock=10)
        self.assertEqual(b.used,0);self.assertEqual(b.phase,'verifying')
    def test_inventory_drop_counts_once_and_animation_blocks(self):
        b=self.make();self.submitted(b)
        self.stable(b,20,stock=9,motion=True,luck=5)
        self.assertEqual(b.used,1)
        a=self.tick(b,34,stock=9,motion=True,luck=5)
        self.assertEqual(a.kind,'wait');self.assertEqual(b.phase,'verifying')
        self.stable(b,35,stock=9,luck=5)
        self.tick(b,37.5,stock=9,luck=5)
        self.assertIsNone(b.phase);self.assertEqual(b.used,1)
    def test_long_animation_no_eight_second_timeout(self):
        b=self.make();self.submitted(b)
        self.assertEqual(self.tick(b,30,state='unknown',motion=True).kind,'wait')
    def test_ambiguous_result_stops_not_retries(self):
        b=self.make();self.submitted(b)
        self.assertEqual(self.tick(b,54.1).kind,'stop');self.assertEqual(b.used,0)
    def test_cap_dismiss_no_consumption(self):
        b=self.make();self.submitted(b)
        a=self.tick(b,19,state='bait_menu',cap=True)
        self.assertEqual(a.purpose,'bait_dismiss')
        self.stable(b,20,luck=5);self.tick(b,22.4,luck=5)
        self.assertIsNone(b.phase);self.assertEqual(b.used,0)
    def test_cap_with_low_luck_does_not_learn_false_ceiling(self):
        b=self.make();self.submitted(b);self.tick(b,19,state='bait_menu',cap=True)
        self.stable(b,20,luck=4)
        self.assertEqual(self.tick(b,22.4,luck=4).kind,'wait')
        self.assertEqual(b.target,5);self.assertEqual(b.phase,'closing')
    def test_full_before_confirmation_cancels_popup(self):
        b=self.make();self.opening(b)
        self.stable(b,19,luck=5,state='bait_menu')
        self.assertEqual(b.phase,'closing');self.assertEqual(b.used,0)
    def test_budget_spent_continues_without_stop_option(self):
        b=self.make(bait_limit=1);b.used=1;self.stable(b)
        self.stable(b,18);self.assertIsNone(self.tick(b,20));self.assertIsNone(b.phase)
    def test_budget_spent_keeps_fishing_until_expiry(self):
        b=self.make(bait_limit=1,stop_on_bait_end=True);b.used=1
        self.assertIsNone(self.stable(b))
        self.stable(b,18);self.assertIsNone(self.tick(b,20))
        self.assertEqual(self.stable(b,22,luck=1).purpose,'auto_stop')
    def test_zero_budget_unlimited(self):
        b=self.make(bait_limit=0);b.used=500;self.opening(b);self.assertFalse(b.at_limit())
    def test_missing_bait_with_stop_off_does_not_stop(self):
        b=self.make();self.stable(b,stock=0);self.stable(b,18,stock=0)
        self.assertIsNone(self.tick(b,20,stock=0));self.assertIsNone(b.phase)
    def test_uncertain_grade_never_spends(self):
        b=self.make();self.stable(b,level=None)
        self.assertEqual(self.tick(b,12,level=None).kind,'stop');self.assertIsNone(b.phase)
    def test_cached_sample_does_not_fake_stability(self):
        b=self.make();o=obs(0)
        for t in (0,.4,.8):b.observe(o,t)
        self.assertFalse(b.fresh)
    def test_glint_blocks_luck_confirmation(self):
        b=self.make();self.stable(b,luck=5,motion=True);self.assertIsNone(b.current)
    def test_invalid_luck_above_rod_cap_not_accepted(self):
        b=self.make();self.stable(b,luck=7,level=1);self.assertFalse(b.fresh)
    def test_completed_fish_not_interrupted_when_luck_drops(self):
        e=Engine(Settings(auto_bait=True,stop_on_bait_end=True))
        o=obs(1,state='fight');o.in_yellow=True
        self.assertEqual(e.step(o,1).purpose,'fight')
    def test_timer_has_no_effect(self):
        b=self.make();self.stable(b,luck=5)
        o=obs(2,luck=5);o.timer='absent';b.observe(o,2)
        self.assertIsNone(b.action(o,2,Action,ready=True))


    def test_buff_expiry_waits_for_base_luck_without_spending(self):
        b=BaitMaintenance(Settings(auto_bait=False,stop_when_buffs_end=True),delay=lambda:2.)
        self.assertIsNone(self.stable(b,luck=2))
        self.assertIsNone(b.phase)
        result=self.stable(b,3,luck=1)
        self.assertEqual(result.purpose,'auto_stop');self.assertEqual(b.used,0)

    def test_expiry_requires_fresh_reading_and_ready_boundary(self):
        b=BaitMaintenance(Settings(stop_when_buffs_end=True))
        self.stable(b,luck=3)
        result=self.tick(b,3,luck=1)
        self.assertEqual(result.kind,'wait')
        self.assertIsNone(self.tick(b,4,luck=1,state='fighting'))
        self.assertEqual(self.stable(b,5,luck=1).purpose,'auto_stop')

    def test_both_stop_conditions_wait_for_full_expiry(self):
        b=BaitMaintenance(Settings(stop_when_buffs_end=True,stop_on_bait_end=True),delay=lambda:2.)
        self.stable(b,luck=2)
        result=self.stable(b,18,luck=2)
        self.assertIsNone(result)
        self.assertEqual(self.stable(b,20,luck=1).purpose,'auto_stop')

    def test_red_level_and_luck_pipeline_simulation(self):
        b=BaitMaintenance(Settings(auto_bait=False))
        self.stable(b,luck=4,level=4)
        self.assertEqual(b.snapshot()['rodLevel'],4)
        self.assertEqual(b.snapshot()['luckCurrent'],4)
        self.assertEqual(b.snapshot()['luckTarget'],8)

    def test_absent_icon_skips_team_grace_and_clears_existing_wait(self):
        b=self.make();self.stable(b)
        self.assertIsNotNone(b.deadline)
        o=obs(1.2,stock=10);o.bait_available=False;b.observe(o,1.2)
        self.assertIsNone(b.action(o,1.2,Action,ready=True))
        self.assertIsNone(b.deadline);self.assertIsNone(b.phase)
        self.assertNotIn('等待队友',b.status)

    def test_absent_icon_continues_until_expiry_without_team_grace(self):
        b=self.make(stop_on_bait_end=True)
        result=self.stable(b,stock=0)
        self.assertIsNone(result);self.assertIsNone(b.deadline)
        self.assertEqual(self.stable(b,2,stock=0,luck=1).purpose,'auto_stop')

    def test_icon_return_starts_new_wait_and_never_uses_old_deadline(self):
        b=self.make();self.stable(b,stock=0)
        self.assertIsNone(b.deadline)
        result=self.stable(b,2,stock=3)
        self.assertEqual(result.kind,'wait');self.assertGreater(b.deadline,18)
        self.assertIsNone(b.phase)

    def test_insufficient_stock_preserves_bait_until_base(self):
        b=self.make(bait_limit=0,stop_on_bait_end=True)
        self.assertIsNone(self.stable(b,level=3,luck=4,stock=2))
        self.assertIsNone(b.phase);self.assertIsNone(b.deadline)
        self.assertEqual(self.stable(b,3,level=3,luck=3,stock=2).purpose,'auto_stop')
        self.assertEqual(b.used,0)

    def test_remaining_budget_must_cover_entire_deficit(self):
        b=self.make(bait_limit=4,stop_on_bait_end=True);b.used=2
        self.assertIsNone(self.stable(b,luck=2,stock=10))
        self.assertIsNone(b.phase)

    def test_exact_capacity_and_unlimited_budget_allow_refill(self):
        for limit in (0,3):
            b=self.make(bait_limit=limit,stop_on_bait_end=True)
            self.stable(b,luck=2,stock=3)
            self.stable(b,18,luck=2,stock=3)
            self.assertEqual(b.phase,'opening')

    def test_team_increase_can_make_supply_sufficient(self):
        b=self.make(bait_limit=0,stop_on_bait_end=True)
        self.assertIsNone(self.stable(b,luck=2,stock=2))
        self.stable(b,3,luck=3,stock=2)
        self.assertIsNotNone(b.deadline)
        self.stable(b,22,luck=3,stock=2)
        self.assertEqual(b.phase,'opening')

    def test_budget_reduction_before_confirmation_cancels(self):
        b=self.make(bait_limit=0,stop_on_bait_end=True)
        self.stable(b,luck=2);self.stable(b,18,luck=2)
        b.settings.bait_limit=2
        a=self.tick(b,19,luck=2,state='bait_menu')
        self.assertEqual(a.purpose,'bait_cancel');self.assertEqual(b.used,0)

    def test_without_policy_partial_bait_still_allowed(self):
        b=self.make(bait_limit=0)
        self.stable(b,luck=2,stock=1);self.stable(b,18,luck=2,stock=1)
        self.assertEqual(b.phase,'opening')

    def test_unknown_inventory_does_not_spend_or_auto_stop(self):
        b=self.make(bait_limit=0,stop_on_bait_end=True)
        self.stable(b,luck=2,stock=None)
        a=self.stable(b,18,luck=2,stock=None)
        self.assertEqual(a.kind,'wait');self.assertIsNone(b.phase)

    def test_exhausted_budget_does_not_need_inventory(self):
        b=self.make(bait_limit=1,stop_on_bait_end=True);b.used=1
        self.assertIsNone(self.stable(b,luck=2,stock=None))
        self.assertIsNone(b.deadline)

    def test_protection_only_keeps_fishing_even_when_all_buffs_expire(self):
        b=self.make(bait_limit=0,full_bait_protection=True)
        self.assertIsNone(self.stable(b,luck=2,stock=2))
        self.assertIsNone(self.stable(b,3,luck=1,stock=2))
        self.assertIsNone(b.phase);self.assertEqual(b.used,0)

    def test_saved_stock_reaching_deficit_resumes_bait(self):
        b=self.make(bait_limit=0,full_bait_protection=True)
        self.stable(b,luck=1,stock=3)
        self.assertIsNone(b.deadline)
        self.stable(b,3,luck=1,stock=4)
        self.assertIsNotNone(b.deadline)
        self.stable(b,22,luck=1,stock=4)
        self.assertEqual(b.phase,'opening')

    def test_protection_counts_budget_and_team_buffs(self):
        b=self.make(bait_limit=2,full_bait_protection=True)
        self.assertIsNone(self.stable(b,luck=2,stock=10))
        self.stable(b,3,luck=3,stock=10)
        self.stable(b,22,luck=3,stock=10)
        self.assertEqual(b.phase,'opening')

    def test_protection_enabled_during_opening_cancels_insufficient_attempt(self):
        b=self.make(bait_limit=0)
        self.stable(b,luck=1,stock=1);self.stable(b,18,luck=1,stock=1)
        b.settings.full_bait_protection=True
        self.assertEqual(self.tick(b,19,luck=1,stock=1,state='bait_menu').purpose,'bait_cancel')

    def test_runtime_disable_protection_allows_partial_refill(self):
        b=self.make(bait_limit=0,full_bait_protection=True)
        self.stable(b,luck=1,stock=1)
        b.settings.full_bait_protection=False
        self.stable(b,3,luck=1,stock=1);self.stable(b,22,luck=1,stock=1)
        self.assertEqual(b.phase,'opening')

    def test_both_protection_and_stop_wait_until_expired(self):
        b=self.make(bait_limit=0,full_bait_protection=True,stop_on_bait_end=True)
        self.assertIsNone(self.stable(b,luck=2,stock=1))
        self.assertEqual(self.stable(b,3,luck=1,stock=1).purpose,'auto_stop')
