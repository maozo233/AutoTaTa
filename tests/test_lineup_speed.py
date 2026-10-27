"""Gesture latency, page-by-page searching, and stable inventory positions."""
import threading,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import numpy as np
from lineup.input import drag
from tests import test_lineup as helpers


class DragTimingTests(unittest.TestCase):
    def test_controller_work_is_included_in_gesture_deadline(self):
        clock=[0.];points=[];done=SimpleNamespace(done=True,succeeded=True)
        def move(x,y,**kw):clock[0]+=.012;points.append((x,y));return done
        def wait(seconds):clock[0]+=seconds;return False
        controller=Mock();controller.post_touch_down.return_value=done
        controller.post_touch_up.return_value=done;controller.post_touch_move.side_effect=move
        session=SimpleNamespace(size=(900,1600),controller=controller,validate=Mock(return_value=True))
        cancel=Mock();cancel.is_set.return_value=False;cancel.wait.side_effect=wait
        with patch('lineup.input.time.monotonic',side_effect=lambda:clock[0]):
            drag(session,(260,1240),(550,500),cancel,waypoint=(260,950))
        self.assertLessEqual(clock[0],.45)
        self.assertEqual(points[-1],(550,500))
        self.assertTrue(all(x==260 for x,y in points[:3]))
        self.assertLessEqual(abs(points[0][1]-1240),20)
        self.assertTrue(all(x==260 and abs(y-1240)<=92 for x,y in points[:5]))
        controller.post_touch_down.assert_called_once();controller.post_touch_up.assert_called_once()

    def test_slow_or_failed_input_never_leaves_contact_pressed(self):
        done=SimpleNamespace(done=True,succeeded=True)
        controller=Mock();controller.post_touch_down.return_value=done
        controller.post_touch_up.return_value=done;controller.post_touch_move.side_effect=RuntimeError('move failed')
        session=SimpleNamespace(size=(900,1600),controller=controller,validate=Mock(return_value=True))
        with self.assertRaisesRegex(RuntimeError,'move failed'):
            drag(session,(260,1240),(550,500),threading.Event(),waypoint=(260,950))
        controller.post_touch_up.assert_called_once()

    def test_inventory_swipe_slows_before_release_to_limit_inertia(self):
        done=SimpleNamespace(done=True,succeeded=True);c=Mock()
        c.post_touch_down.return_value=done;c.post_touch_move.return_value=done;c.post_touch_up.return_value=done
        session=SimpleNamespace(size=(900,1600),controller=c,validate=Mock(return_value=True))
        cancel=Mock();cancel.is_set.return_value=False;cancel.wait.return_value=False
        drag(session,(750,1080),(90,1080),cancel,220,hold=0,ease_out=True)
        points=[call.args for call in c.post_touch_move.call_args_list]
        self.assertTrue(all(y==1080 for x,y in points))
        self.assertEqual(points[-1],(90,1080))
        self.assertLessEqual(abs(points[-1][0]-points[-2][0]),5)
        self.assertLessEqual(abs(points[0][0]-750),5)
        self.assertTrue(all(a[0]>=b[0] for a,b in zip(points,points[1:])))


class InventoryNavigationTests(unittest.TestCase):
    operations=helpers.ObservationGuardTests.operations

    def setup_search(self,position,identities):
        ops=self.operations();ops.select_element=Mock();ops.rewind=Mock();ops.observation.cards=[{}]
        current=[position];ops.frame[:]=position*30
        def turn(direction):
            after=max(0,min(len(identities)-1,current[0]+direction))
            changed=after!=current[0];current[0]=after;ops.frame[:]=after*30;return changed
        def page(**kw):
            ident=identities[current[0]]
            return [{'id':ident,'point':(40+current[0]*10,180)}] if ident else []
        ops.scroll=Mock(side_effect=turn);ops.page=Mock(side_effect=page)
        return ops,current

    def test_next_page_target_is_found_without_three_rewind_gestures(self):
        ops,pos=self.setup_search(1,[None,None,'dozy',None])
        self.assertEqual(ops.find_available('dozy')['point'],(60,180))
        ops.scroll.assert_called_once_with(1);ops.rewind.assert_not_called()
        self.assertEqual(ops.page.call_count,2)

    def test_reverse_search_finds_earlier_target_without_recognizing_old_pages_twice(self):
        ops,pos=self.setup_search(1,['dozy',None,None])
        self.assertEqual(ops.find_available('dozy')['id'],'dozy')
        self.assertEqual(ops.page.call_count,3)
        self.assertEqual([c.args[0] for c in ops.scroll.call_args_list],[1,1,-1,-1])
        self.assertEqual(ops.search_direction,-1)

    def test_missing_target_terminates_after_both_edges(self):
        ops,pos=self.setup_search(1,[None,None,None])
        self.assertIsNone(ops.find_available('dozy'))
        self.assertEqual(ops.page.call_count,3)
        self.assertEqual(ops.scroll.call_count,5)

    def test_explicit_rewind_stops_after_one_unchanged_swipe(self):
        ops=self.operations();ops.scroll=Mock(return_value=False)
        ops.rewind();ops.scroll.assert_called_once_with(-1)

    def test_scroll_reports_edge_after_two_stable_frames_and_one_gesture(self):
        ops=self.operations();obs=ops.observation
        obs.cards=[{'bounds':(10,160,60,70)},{'bounds':(200,160,60,70)}]
        ops.guard=Mock(return_value=obs);ops.snapshot=Mock(return_value=obs)
        with patch('lineup.runner.drag') as gesture:self.assertFalse(ops.scroll(1))
        gesture.assert_called_once();self.assertEqual(ops.snapshot.call_count,2)

    def test_scroll_waits_out_motion_before_returning_current_card_positions(self):
        ops=self.operations();obs=ops.observation
        obs.cards=[{'bounds':(10,160,60,70)},{'bounds':(200,160,60,70)}]
        ops.guard=Mock(return_value=obs)
        def sample():
            ops.frame[150:]=next(levels);return obs
        levels=iter((150,190,190));ops.snapshot=Mock(side_effect=sample)
        with patch('lineup.runner.drag') as gesture:self.assertTrue(ops.scroll(1))
        gesture.assert_called_once();self.assertEqual(ops.snapshot.call_count,3)

    def test_unstable_inventory_times_out_without_repeating_gesture(self):
        import itertools
        ops=self.operations();obs=ops.observation
        obs.cards=[{'bounds':(10,160,60,70)},{'bounds':(200,160,60,70)}]
        ops.guard=Mock(return_value=obs)
        levels=itertools.cycle((30,190))
        def sample():ops.frame[150:]=next(levels);return obs
        ops.snapshot=Mock(side_effect=sample)
        with patch('lineup.runner.drag') as gesture,patch('lineup.runner.time.monotonic',side_effect=itertools.count()):
            with self.assertRaisesRegex(RuntimeError,'尚未稳定'):ops.scroll(1)
        gesture.assert_called_once()


if __name__=='__main__':unittest.main()
