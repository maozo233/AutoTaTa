import copy,unittest
from unittest.mock import Mock
import numpy as np
from treasure.capture import ObservationConfirmation
from treasure.vision import Observation
from treasure.backend import TreasureBackend

class ConfirmationTests(unittest.TestCase):
    def observation(self,value=2,completed=False):
        mask=np.zeros((160,160),np.uint8);mask[:32,:32]=1
        return Observation((0,0,250,250),5,[value]+[0]*24,(0,0,100,100),[{'box':(20,20,10,30),'mask':np.ones((30,10),np.uint8),'completed':completed}],mask)
    def test_mole_disappearing_after_two_seconds_never_commits(self):
        gate=ObservationConfirmation()
        for now in (0,.5,1,1.5,2):
            result=gate.apply(self.observation(),now)
            self.assertEqual(result.cells[0],-1);self.assertEqual(result.pending_cells,(0,))
            self.assertFalse(result.foreground[:32,:32].any())
        result=gate.apply(self.observation(1),2.1)
        self.assertEqual(result.cells[0],1);self.assertFalse(result.pending_cells)
    def test_real_treasure_confirms_without_mutating_source(self):
        gate=ObservationConfirmation();source=self.observation()
        gate.apply(source,0);result=gate.apply(source,2.4)
        self.assertEqual(result.cells[0],2);self.assertFalse(result.pending_cells)
        self.assertTrue(result.foreground[:32,:32].any());self.assertEqual(source.cells[0],2)
    def test_completion_color_needs_confirmation(self):
        gate=ObservationConfirmation();source=self.observation(1,True)
        self.assertFalse(gate.apply(source,0).silhouettes[0]['completed'])
        self.assertTrue(gate.apply(source,2.4).silhouettes[0]['completed'])
        gate.reset();self.assertFalse(gate.apply(source,3).silhouettes[0]['completed'])
    def test_new_board_discards_pending_candidates(self):
        gate=ObservationConfirmation();source=self.observation();gate.apply(source,0)
        gate.reset();self.assertEqual(gate.apply(source,10).cells[0],-1)

class JointDisappearanceTests(unittest.TestCase):
    def test_final_new_tile_can_disappear_with_confirmed_neighbor_before_delay(self):
        gate=ObservationConfirmation()
        cells=[0]*25;cells[5]=2
        def obs(values):return Observation((0,0,250,250),5,values[:],None,[],np.ones((160,160),np.uint8))
        gate.apply(obs(cells),0);gate.apply(obs(cells),2.4)
        cells[10]=2;new=gate.apply(obs(cells),3)
        self.assertEqual(new.cells[10],-1)
        cells[5]=cells[10]=1;done=gate.apply(obs(cells),3.4)
        self.assertEqual(set(done.completed_cells),{5,10});self.assertFalse(done.transient_cells)
        repeated=gate.apply(obs(cells),3.9);self.assertEqual(set(repeated.completed_cells),{5,10})
        gate.acknowledge();self.assertFalse(gate.apply(obs(cells),4.4).completed_cells)
    def test_neighboring_short_lived_items_have_no_confirmed_anchor(self):
        gate=ObservationConfirmation();cells=[0]*25;cells[5]=cells[10]=2
        o=Observation((0,0,250,250),5,cells,None,[],np.ones((160,160),np.uint8))
        gate.apply(o,0);empty=copy.deepcopy(o);empty.cells[5]=empty.cells[10]=1
        result=gate.apply(empty,1.8)
        self.assertFalse(result.completed_cells);self.assertEqual(set(result.transient_cells),{5,10})

class CompletedHistoryTests(unittest.TestCase):
    def observations(self):
        import cv2
        from pathlib import Path
        from treasure.vision import observe
        frame=cv2.imread(str(Path(__file__).parent/'fixtures/treasure/stage2-partial.png'))
        complete=observe(frame);before=copy.deepcopy(complete)
        for item in before.silhouettes:item['completed']=False
        before.cells[5]=2;before.cells[10]=2;complete.cells[10]=1
        return frame,before,complete
    def test_completed_hit_is_archived_not_reused_as_remaining_hit(self):
        frame,before,complete=self.observations();b=TreasureBackend(discover=False);b.calculate=lambda:None
        b.applyObservation(frame,before,2);b.applyObservation(frame,complete,2)
        self.assertEqual(b.state['cells'][5],1);self.assertIn(5,b.state['completedTreasure'])
        self.assertEqual(b.completed_count,1)
        from treasure.inference import infer
        result=infer(5,b.templates,b.state['cells'],complete.foreground)
        result.update(estimate=None,guided=None);b.overlay_window=Mock();b.finish(b.revision,result)
        self.assertIn(5,b.state['markedTreasure'])
        self.assertIn(5,b.overlay_window.publish.call_args.args[0]['completedTreasure'])
    def test_brief_color_miss_does_not_restore_completed_shape(self):
        frame,before,complete=self.observations();b=TreasureBackend(discover=False);b.calculate=lambda:None
        b.applyObservation(frame,complete,2);expected=b.state['shapes']
        miss=copy.deepcopy(complete)
        for item in miss.silhouettes:item['completed']=False
        b.applyObservation(frame,miss,2)
        self.assertEqual(b.state['shapes'],expected);self.assertEqual(b.completed_count,1)
        b.applyObservation(frame,complete,2);self.assertEqual(b.state['shapes'],expected)
    def test_delayed_despawn_still_archives_confirmed_cell(self):
        frame,before,complete=self.observations();b=TreasureBackend(discover=False);b.calculate=lambda:None
        b.applyObservation(frame,before,2)
        early=copy.deepcopy(complete);early.cells[5]=2;early.cells[10]=2
        b.applyObservation(frame,early,2);self.assertNotIn(5,b.state['completedTreasure'])
        b.applyObservation(frame,complete,2);self.assertIn(5,b.state['completedTreasure']);self.assertEqual(b.state['cells'][5],1)
    def test_next_board_resets_history_and_completed_slots(self):
        frame,before,complete=self.observations();b=TreasureBackend(discover=False);b.calculate=lambda:None
        b.applyObservation(frame,before,2);b.applyObservation(frame,complete,2)
        b.applyObservation(frame,before,{'stage':2,'newSession':True})
        self.assertFalse(b.state['completedTreasure']);self.assertEqual(b.completed_count,0);self.assertFalse(b.state['completedSlots'])
    def test_transient_mole_does_not_enter_backend_history(self):
        frame,before,complete=self.observations();b=TreasureBackend(discover=False);b.calculate=lambda:None
        gate=ObservationConfirmation()
        for now in (0,.5,1,1.5,2):b.applyObservation(frame,gate.apply(before,now),2)
        clean=copy.deepcopy(before);clean.cells[5]=1
        b.applyObservation(frame,gate.apply(clean,2.1),2)
        b.applyObservation(frame,gate.apply(clean,3.0),2)
        self.assertEqual(b.state['cells'][5],1);self.assertNotIn(5,b.state['treasureHistory'])
        self.assertNotIn(5,b.state['completedTreasure'])
        self.assertIn(1,b.state['treasureHistory'])
    def test_manual_hit_becomes_completed_history_and_can_be_cleared(self):
        frame,before,complete=self.observations();b=TreasureBackend(discover=False);b.calculate=lambda:None
        b.applyObservation(frame,before,2);b.mark(5,2);b.applyObservation(frame,complete,2)
        self.assertEqual(b.state['cells'][5],1);self.assertIn(5,b.state['completedTreasure'])
        self.assertNotIn(5,b.overrides)
        b.mark(5,1);self.assertNotIn(5,b.state['completedTreasure']);self.assertNotIn(5,b.state['treasureHistory'])
    def test_ground_completion_precedes_color_without_double_deducting(self):
        frame,before,complete=self.observations();b=TreasureBackend(discover=False);b.calculate=lambda:None
        b.applyObservation(frame,before,2)
        ground=copy.deepcopy(complete)
        for item in ground.silhouettes:item['completed']=False
        b.applyObservation(frame,ground,2)
        self.assertEqual(b.completed_count,1);self.assertEqual(b.state['shapes'],[[1,2,2],[2,2,1]])
        self.assertEqual(set(b.state['completedTreasure']),{5,10})
        b.applyObservation(frame,complete,2)
        self.assertEqual(b.completed_count,1);self.assertEqual(b.state['shapes'],[[1,2,2],[2,2,1]])
    def test_opened_empty_prediction_is_rejected_not_archived(self):
        frame,before,complete=self.observations();b=TreasureBackend(discover=False);b.calculate=lambda:None
        b.applyObservation(frame,before,2)
        b._state['predictedTreasure']=[0,5];b._state['candidateTreasure']=[0]
        b._state['ghostItems']=[dict(x=0,y=0,w=1,h=2,support=1,certain=True,pinned=False)]
        opened=copy.deepcopy(before);opened.cells[0]=1
        b.applyObservation(frame,opened,2)
        self.assertIn(0,b.dismissed_predictions);self.assertNotIn(0,b.state['treasureHistory'])
        self.assertNotIn(0,b.state['completedTreasure']);self.assertEqual(b.state['cells'][0],1)
    def test_long_single_item_disappearing_alone_is_removed_from_history(self):
        frame,before,complete=self.observations();before.cells[10]=1
        b=TreasureBackend(discover=False);b.calculate=lambda:None;b.applyObservation(frame,before,2)
        empty=copy.deepcopy(before);empty.cells[5]=1
        b.applyObservation(frame,empty,2)
        self.assertEqual(b.state['cells'][5],1);self.assertNotIn(5,b.state['treasureHistory'])
        self.assertNotIn(5,b.state['completedTreasure']);self.assertEqual(b.completed_count,0)
    def test_all_colored_completed_stops_remaining_calculation(self):
        frame,before,complete=self.observations();b=TreasureBackend(discover=False);b.calculate=lambda:None
        for item in complete.silhouettes:item['completed']=True
        complete.cells=[1 if v==2 else v for v in complete.cells]
        b.applyObservation(frame,complete,2);self.assertFalse(b.state['shapes'])
        from treasure.solver import solve
        result=solve(5,[],b.state['cells']);result.update(estimate=None,guided=None)
        b.finish(b.revision,result)
        self.assertTrue(b.state['allIdentified']);self.assertTrue(b.state['allLocated'])
        self.assertEqual(b.state['probabilities'],[None]*25)
        b.applyObservation(frame,complete,2);self.assertTrue(b.state['allLocated'])

    def scoped_event(self,allowed,marked=(),event=(5,10)):
        frame,before,complete=self.observations()
        before.cells=[0]*25
        for i in marked:before.cells[i]=2
        for item in complete.silhouettes:item['completed']=False
        complete.cells=before.cells[:]
        for i in event:complete.cells[i]=1
        complete.completed_cells=event
        b=TreasureBackend(discover=False);b.calculate=lambda:None
        b.applyObservation(frame,before,2)
        b._state['predictedTreasure']=list(allowed)
        return b,frame,before,complete
    def test_joint_event_outside_prior_treasure_scope_is_not_completed(self):
        b,frame,before,complete=self.scoped_event([])
        b.applyObservation(frame,complete,2)
        self.assertFalse(b.state['completedTreasure']);self.assertFalse(b.state['completedGroups'])
        self.assertEqual(b.completed_count,0);self.assertEqual(b.state['cells'][5],1)
    def test_one_marked_cell_cannot_complete_with_unscoped_neighbor(self):
        b,frame,before,complete=self.scoped_event([],marked=(5,))
        b.applyObservation(frame,complete,2)
        self.assertFalse(b.state['completedTreasure']);self.assertEqual(b.completed_count,0)
        self.assertNotIn(5,b.state['treasureHistory'])
    def test_predicted_final_tile_can_complete_with_marked_neighbor(self):
        b,frame,before,complete=self.scoped_event([10],marked=(5,))
        b.applyObservation(frame,complete,2)
        self.assertEqual(set(b.state['completedTreasure']),{5,10});self.assertEqual(b.completed_count,1)
        self.assertNotIn(10,b.dismissed_predictions)
    def test_unscoped_cell_cannot_bridge_scoped_cells(self):
        b,frame,before,complete=self.scoped_event([5,15],event=(5,10,15))
        b.applyObservation(frame,complete,2)
        self.assertFalse(b.state['completedTreasure']);self.assertEqual(b.completed_count,0)
    def test_joint_event_archives_only_scoped_neighbors(self):
        b,frame,before,complete=self.scoped_event([5,10],event=(5,10,15))
        b.applyObservation(frame,complete,2)
        self.assertEqual(set(b.state['completedTreasure']),{5,10})
        self.assertNotIn(15,b.state['treasureHistory']);self.assertEqual(b.completed_count,1)
    def test_scope_survives_calculation_invalidation(self):
        b,frame,before,complete=self.scoped_event([10],marked=(5,))
        b.invalidate();self.assertFalse(b.state['predictedTreasure'])
        b.applyObservation(frame,complete,2)
        self.assertEqual(set(b.state['completedTreasure']),{5,10});self.assertEqual(b.completed_count,1)
    def test_new_board_does_not_reuse_previous_completion_scope(self):
        b,frame,before,complete=self.scoped_event([5,10])
        b.invalidate();b.applyObservation(frame,complete,{'stage':2,'newSession':True})
        self.assertFalse(b.state['completedTreasure']);self.assertEqual(b.completed_count,0)
    def test_repeated_joint_event_is_not_counted_twice(self):
        b,frame,before,complete=self.scoped_event([10],marked=(5,))
        b.applyObservation(frame,complete,2);b.applyObservation(frame,complete,2)
        self.assertEqual(set(b.state['completedTreasure']),{5,10});self.assertEqual(b.completed_count,1)
        self.assertEqual(len(b.state['completedGroups']),1)

    def test_confirmed_catalog_keeps_live_completion_tracking(self):
        frame,before,complete=self.observations();b=TreasureBackend(discover=False);b.calculate=lambda:None
        b.applyObservation(frame,before,2);self.assertTrue(b.confirmTreasures())
        b.applyObservation(frame,complete,2)
        self.assertEqual(b.completed_count,1);self.assertEqual(set(b.state['completedTreasure']),{5,10})
        self.assertTrue(b.state['treasuresConfirmed'])
