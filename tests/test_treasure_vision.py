import unittest,json,time
from pathlib import Path
import cv2,numpy as np
from treasure.vision import observe,assign_templates,infer_dimensions
from treasure.inference import infer,options_for
from treasure.backend import TreasureBackend

ROOT=Path(__file__).resolve().parents[1]
class RecognitionTests(unittest.TestCase):
    def frame(self,name):return cv2.imread(str(ROOT/'tests/fixtures/treasure'/name))
    def test_unopened_stage10_and_resize(self):
        frame=self.frame('stage10.png')
        for factor in (1,.75,1.4):
            obs=observe(cv2.resize(frame,None,fx=factor,fy=factor))
            self.assertIsNotNone(obs);self.assertEqual(obs.size,7);self.assertEqual(obs.cells,[0]*49)
            self.assertEqual(len(obs.silhouettes),5)
            ts=assign_templates(obs.silhouettes,[[1,4,2],[3,3,1],[1,2,2]])
            self.assertEqual(len(ts),5)
    def test_cold_start_partial_board_without_hint(self):
        frame=self.frame('stage2-cold-start.png')
        for scale in (.75,1,1.4):
            with self.subTest(scale=scale):
                obs=observe(cv2.resize(frame,None,fx=scale,fy=scale))
                self.assertIsNotNone(obs);self.assertEqual(obs.size,5)
                self.assertEqual(len(obs.cells),25)
                self.assertAlmostEqual(obs.rect[2],262*scale,delta=2)
                self.assertEqual(obs.cells[8],2)

    def test_larger_sparse_board_cold_start(self):
        frame=self.frame('stage10.png');base=observe(frame);x,y,w,h=base.rect
        keep={(0,0),(0,6),(6,0),(6,6),(2,4),(4,4)}
        for row in range(7):
            for col in range(7):
                if (row,col) not in keep:
                    frame[round(y+row*h/7):round(y+(row+1)*h/7),round(x+col*w/7):round(x+(col+1)*w/7)]=(69,65,95)
        for scale in (.75,1,1.4):
            with self.subTest(scale=scale):
                obs=observe(cv2.resize(frame,None,fx=scale,fy=scale))
                self.assertIsNotNone(obs);self.assertEqual(obs.size,7)
                self.assertEqual(obs.cells.count(0),6);self.assertEqual(obs.cells.count(1),43)

    def test_opened_cells(self):
        obs=observe(self.frame('opened.png'))
        self.assertEqual(obs.size,6)
        self.assertEqual([i for i,v in enumerate(obs.cells) if v==1],[1,16,17,25])
        self.assertEqual([i for i,v in enumerate(obs.cells) if v==2],[14])
        self.assertEqual(len(obs.silhouettes),5)
    def test_previously_verified_board_survives_mostly_opened_tiles(self):
        frame=self.frame('live-stage1.png');hint=observe(frame);x,y,w,h=hint.rect
        opened=frame.copy();opened[y:y+h,x:x+w]=(69,65,95)
        for row in range(5):
            for col in range(5):
                if (row,col)==(2,2):
                    opened[round(y+row*h/5):round(y+(row+1)*h/5),round(x+col*w/5):round(x+(col+1)*w/5)]=frame[round(y+row*h/5):round(y+(row+1)*h/5),round(x+col*w/5):round(x+(col+1)*w/5)]
        result=observe(opened,hint)
        self.assertIsNotNone(result);self.assertEqual(result.size,5);self.assertEqual(result.cells.count(1),24)
        self.assertIsNone(observe(self.frame('lobby.png'),hint))
    def test_mid_stage_sparse_board_and_completed_tray(self):
        frame=self.frame('stage2-partial.png')
        for scale in (.75,1,1.4):
            with self.subTest(scale=scale):
                obs=observe(cv2.resize(frame,None,fx=scale,fy=scale))
                self.assertIsNotNone(obs);self.assertEqual(obs.size,5)
                self.assertEqual(sum(bool(s.get('completed')) for s in obs.silhouettes),1)
                b=TreasureBackend(discover=False);b.calculate=lambda:None;b.applyObservation(None,obs,2)
                self.assertEqual(b.state['shapes'],[[1,2,2],[2,2,1]])
                self.assertIsNotNone(infer(5,b.templates,b.state['cells'],obs.foreground))
                b.applyObservation(None,obs,2);self.assertEqual(b.completed_count,1)

    def test_real_sdk_partial_board(self):
        obs=observe(self.frame('stage2-partial-sdk.png'))
        self.assertIsNotNone(obs);self.assertEqual(obs.size,5)
        b=TreasureBackend(discover=False);b.calculate=lambda:None;b.applyObservation(None,obs,2)
        self.assertEqual(b.completed_count,1);self.assertEqual(b.state['shapes'],[[1,2,2],[2,2,1]])

    def test_completed_item_releases_vanished_occupancy(self):
        import copy
        obs=observe(self.frame('stage2-partial.png'));before=copy.deepcopy(obs)
        for item in before.silhouettes:item['completed']=False
        before.cells[5]=2
        b=TreasureBackend(discover=False);b.calculate=lambda:None;b.applyObservation(None,before,2)
        b.applyObservation(None,obs,2)
        self.assertEqual(b.state['cells'][5],1);self.assertEqual(b.state['cells'][1],2)

    def test_overlay_keeps_board_and_hits_while_recalculating(self):
        from unittest.mock import Mock
        b=TreasureBackend(discover=False);b.calculate=lambda:None
        obs=observe(self.frame('stage2-partial.png'));b.applyObservation(None,obs,2)
        b.overlay_window=Mock();b.invalidate()
        payload=b.overlay_window.publish.call_args.args[0]
        self.assertEqual(payload['size'],5);self.assertEqual(payload['rect'],obs.rect)
        self.assertEqual(payload['cells'][1],2);self.assertEqual(payload['probabilities'],[])

    def test_ghost_marks_do_not_change_opened_cells(self):
        from treasure.solver import solve,estimate,estimate_guided
        b=TreasureBackend(discover=False);b.configure(3,15,'1x2:1')
        cells=b.state['cells'][:];r=solve(3,[[1,2,1]],cells)
        r['ghosts']=[dict(x=0,y=0,w=2,h=1,certain=False,support=.95,pinned=False,image=np.ones((32,64),np.uint8))]
        r['estimate']=estimate(r['masks'],cells,15);r['guided']=estimate_guided(r['masks'],cells,15)
        b.finish(b.revision,r)
        self.assertEqual(b.state['predictedTreasure'],[0,1]);self.assertEqual(b.state['certainTreasure'],[])
        self.assertEqual(b.state['cells'],cells)
        b.mark(0,1);self.assertEqual(b.state['predictedTreasure'],[])

    def test_board_heartbeat_independent_of_stable_results(self):
        from unittest.mock import Mock
        b=TreasureBackend(discover=False);b.overlay_window=Mock();b.generation=3;b.live['running']=True
        b.boardSeen(2);b.overlay_window.heartbeat.assert_not_called()
        b.boardSeen(3);b.overlay_window.heartbeat.assert_called_once()
        b.setOverlay(True);b.overlay_window.setEnabled.assert_called_with(True)
        b.setOverlay(False);b.overlay_window.setEnabled.assert_called_with(False)

    def test_lobby_not_board(self):self.assertIsNone(observe(self.frame('lobby.png')))
    def test_live_first_stage_disagrees_with_reference(self):
        obs=observe(self.frame('live-stage1.png'))
        self.assertEqual(obs.size,5);self.assertEqual(len(obs.silhouettes),4)
        self.assertEqual(infer_dimensions(obs.silhouettes,5),[[1,2,4]])
        backend=TreasureBackend(discover=False);backend.calculate=lambda:None
        backend.applyObservation(self.frame('live-stage1.png'),obs,1)
        self.assertEqual(backend.state['shapes'],[[1,2,4]])
    def test_manual_override_survives_live_and_undo(self):
        obs=observe(self.frame('stage10.png'));b=TreasureBackend(discover=False);b.calculate=lambda:None
        b.applyObservation(self.frame('stage10.png'),obs,10)
        b.mark(0,1);b.applyObservation(None,obs,10);self.assertEqual(b.state['cells'][0],1)
        b.undo();b.applyObservation(None,obs,10);self.assertEqual(b.state['cells'][0],0)
    def test_single_disappearance_is_empty_and_manual_correction_wins(self):
        import copy
        obs=observe(self.frame('opened.png'));b=TreasureBackend(discover=False);b.calculate=lambda:None
        b.configure(6,15,'1x2:3');b.applyObservation(None,obs,None)
        self.assertEqual(b.state['cells'][14],2)
        vanished=copy.deepcopy(obs);vanished.cells[14]=1;vanished.foreground[:]=0
        b.applyObservation(None,vanished,None)
        self.assertEqual(b.state['cells'][14],1)
        self.assertNotIn(14,b.state['completedTreasure'])
        b.mark(14,1);b.applyObservation(None,vanished,None)
        self.assertEqual(b.state['cells'][14],1)
        b.selectStage(1);self.assertTrue(all(v==0 for v in b.state['cells']))

    def test_exact_inference_marks_only_structural_certainty(self):
        mask=np.ones((32,64),np.uint8)
        result=infer(3,[{'mask':mask}],[2,0,1,1,1,1,1,1,1],np.zeros((96,96),np.uint8))
        self.assertEqual(result['certainCells'],[0,1])
        sampled=infer(3,[{'mask':mask}],[0]*9,np.zeros((96,96),np.uint8),node_limit=1,samples=1)
        self.assertFalse(sampled['exact']);self.assertEqual(sampled['certainCells'],[])

    def test_certain_unopened_cell_keeps_consumption(self):
        from treasure.solver import solve,estimate,estimate_guided
        b=TreasureBackend(discover=False);b.configure(3,15,'1x2:1')
        b._state['cells']=[2,0,1,1,1,1,1,1,1]
        result=solve(3,[[1,2,1]],b.state['cells'])
        result['estimate']=estimate(result['masks'],b.state['cells'],15)
        result['guided']=estimate_guided(result['masks'],b.state['cells'],15)
        b.finish(b.revision,result)
        self.assertEqual(b.state['certainTreasure'],[0,1])
        self.assertEqual(b.state['cells'][1],0)
        self.assertEqual(result['estimate']['cost'],15)
        b.mark(1,1);self.assertEqual(b.state['certainTreasure'],[])

    def test_manual_configuration_not_overwritten(self):
        obs=observe(self.frame('live-stage1.png'));b=TreasureBackend(discover=False);b.calculate=lambda:None
        b.configure(5,17,'1x2:2');b.applyObservation(None,obs,1)
        self.assertEqual(b.state['shapes'],[[1,2,2]]);self.assertEqual(b.state['cost'],17)
    def test_symmetric_evidence_keeps_ambiguity(self):
        template={'mask':np.ones((32,64),np.uint8)}
        result=infer(3,[template],[0]*9,np.zeros((96,96),np.uint8))
        self.assertTrue(result['exact']);self.assertEqual(result['ghosts'],[])
        self.assertAlmostEqual(sum(result['probabilities']),2)
    def test_asymmetric_fragment_favors_orientation(self):
        mask=np.zeros((32,64),np.uint8);mask[6:26,6:26]=1;mask[12:20,32:58]=1
        foreground=np.zeros((96,96),np.uint8);foreground[:32,:32]=mask[:,:32]
        result=infer(3,[{'mask':mask}],[2,0,1,1,1,1,1,1,1],foreground)
        self.assertEqual(result['probabilities'][:2],[1.,1.])
        self.assertTrue(result['ghosts']);self.assertGreater(result['ghosts'][0]['support'],.5)
    def test_empty_cells_exclude_placements(self):
        choices=options_for(3,{'mask':np.ones((32,64),np.uint8)},[1]+[0]*8,np.zeros((96,96),np.uint8))
        self.assertTrue(choices);self.assertTrue(all(not o['mask']&1 for o in choices))
    def test_manual_pin_sets_location_without_revealed_fragment(self):
        result=infer(3,[{'mask':np.ones((32,64),np.uint8)}],[0]*9,np.zeros((96,96),np.uint8),pins={0:{'x':1,'y':2,'turn':0}})
        self.assertEqual(result['probabilities'],[0,0,0,0,0,0,0,1,1]);self.assertTrue(result['ghosts'][0]['pinned'])
    def test_pin_conflicting_with_empty_returns_no_layout(self):
        result=infer(3,[{'mask':np.ones((32,64),np.uint8)}],[1]+[0]*8,np.zeros((96,96),np.uint8),pins={0:{'x':0,'y':0,'turn':0}})
        self.assertIsNone(result)
    def test_offline_change_queues_new_calculation(self):
        from unittest.mock import patch
        b=TreasureBackend(discover=False);b.busy=True;b.calculate()
        old=b.revision;b.revision+=1
        with patch.object(b,'calculate') as calculate:
            b.finish(old,{})
            calculate.assert_called_once()
    def test_configuration_undo_restores_manual_piece_data(self):
        b=TreasureBackend(discover=False);b.templates=[{'mask':np.ones((32,64),np.uint8)}];b.pins={0:{'x':0,'y':0,'turn':0}}
        b.configure(6,20,'1x2:3');b.undo()
        self.assertEqual(b.state['size'],5);self.assertEqual(len(b.templates),1);self.assertIn(0,b.pins)
    def test_joint_probability_area_and_nonoverlap(self):
        result=infer(3,[{'mask':np.ones((32,64),np.uint8)}]*2,[0]*9,np.zeros((96,96),np.uint8))
        self.assertTrue(all(m.bit_count()==4 for m in result['masks']))
        self.assertAlmostEqual(sum(result['probabilities']),4)

if __name__=='__main__':unittest.main()


class SilhouetteOccupancyTests(unittest.TestCase):
    def test_thin_connected_tip_counts_next_grid_cell(self):
        from treasure.vision import silhouette_occupancy,infer_dimensions
        mask=np.zeros((20,41),np.uint8);mask[3:17,:39]=1;mask[9:11,39:]=1
        occupied=silhouette_occupancy(mask,20)
        self.assertEqual(occupied.tolist(),[[1,1,1]])
        self.assertEqual(infer_dimensions([{'mask':mask,'box':(0,0,41,20)}],5,(0,0,140,140)),[[1,3,1]])

    def test_detached_noise_does_not_add_grid_cell(self):
        from treasure.vision import silhouette_occupancy
        mask=np.zeros((20,60),np.uint8);mask[3:17,:38]=1;mask[0,59]=1
        self.assertEqual(silhouette_occupancy(mask,20).tolist(),[[1,1]])

    def test_supplied_partial_board_reads_opened_dirt(self):
        obs=observe(cv2.imread(str(ROOT/'tests/fixtures/treasure/stage1-three-treasures.png')))
        self.assertEqual(obs.size,5);self.assertEqual(len(obs.silhouettes),3)
        self.assertEqual([i for i,v in enumerate(obs.cells) if v==1],[0,6,12,18])


class OpenedTileAndOverlayTests(unittest.TestCase):
    def test_gold_treasure_fills_opened_tile(self):
        from treasure.vision import Observation
        frame=cv2.imread(str(ROOT/'tests/fixtures/treasure/stage1-gold-treasure.png'))
        hint=Observation((139,529,262,271),5,[],None,[],np.zeros((160,160),np.uint8),frame.shape[:2])
        obs=observe(frame,hint)
        self.assertEqual(obs.cells[2],2)
        self.assertEqual([i for i,v in enumerate(obs.cells) if v==2],[2,9,22])
        self.assertEqual([i for i,v in enumerate(obs.cells) if v==1],[6,10,12,16,18])
        self.assertNotIn(-1,obs.cells)

    def test_overlay_retains_probabilities_until_new_result(self):
        from unittest.mock import Mock
        b=TreasureBackend(discover=False);b.calculate=lambda:None
        obs=observe(cv2.imread(str(ROOT/'tests/fixtures/treasure/live-stage1.png')))
        b.applyObservation(None,obs,1)
        payload={'size':5,'cells':obs.cells[:],'rect':obs.rect,'probabilities':[.25]*25}
        b.overlay_window=Mock();b.overlay_window.data=payload
        b.live['running']=True;b.boardChanged(b.generation);b.invalidate()
        b.overlay_window.publish.assert_not_called();b.overlay_window.setEnabled.assert_not_called()
        self.assertEqual(b.overlay_window.data['probabilities'],[.25]*25)
        b.selectStage(10,internal=True)
        b.overlay_window.publish.assert_called_with({})


class ConnectedPartialBoardTests(unittest.TestCase):
    def test_partial_board_recognizes_without_previous_hint(self):
        frame=cv2.imread(str(ROOT/'tests/fixtures/treasure/stage1-connected-partial.png'))
        for scale in (.75,1,1.4):
            with self.subTest(scale=scale):
                obs=observe(cv2.resize(frame,None,fx=scale,fy=scale))
                self.assertIsNotNone(obs);self.assertEqual(obs.size,5)
                self.assertEqual([i for i,v in enumerate(obs.cells) if v==2],[2,9,22])
                self.assertEqual([i for i,v in enumerate(obs.cells) if v==1],[6,10,12,16,18])
                self.assertEqual(len(obs.silhouettes),3)
                self.assertLess(abs(obs.rect[2]-266*scale),6*scale)


class TreasureHypothesisRegressionTests(unittest.TestCase):
    def test_left_bottom_vertical_piece_and_all_identities(self):
        from treasure.vision import Observation
        from unittest.mock import Mock
        frame=cv2.imread(str(ROOT/'tests/fixtures/treasure/stage2-left-bottom.png'))
        hint=Observation((139,489,261,272),5,[],None,[],np.zeros((160,160),np.uint8),frame.shape[:2])
        obs=observe(frame,hint);b=TreasureBackend(discover=False);b.calculate=lambda:None;b.applyObservation(frame,obs,2)
        result=infer(5,b.templates,b.state['cells'],obs.foreground,stop_when_identified=True)
        self.assertTrue(result['exact']);self.assertEqual(result['count'],38784)
        self.assertIn([1,2,3],result['identifiedShapes']);self.assertIn([2,2,1],result['identifiedShapes'])
        left=next(g for g in result['candidateGhosts'] if g['x']==0)
        self.assertEqual((left['y'],left['w'],left['h']),(3,1,2))
        self.assertEqual(result['probabilities'],[None]*25)
        import copy
        weak=copy.deepcopy(result);weak['ghosts']=[];weak['certainCells']=[]
        for item in weak['candidateGhosts']:item['support']=.8;item['certain']=False
        weak.update(estimate=None,guided=None);b.overlay_window=Mock();b.finish(b.revision,weak)
        self.assertTrue(b.state['allIdentified']);self.assertFalse(b.state['allLocated'])
        self.assertEqual(b.state['probabilities'],[None]*25);self.assertEqual(b.state['recommendedCells'],[])
        self.assertEqual(b.overlay_window.publish.call_args.args[0]['probabilities'],[None]*25)
        result.update(estimate=None,guided=None);b.finish(b.revision,result)
        self.assertEqual(b.state['pendingShapes'],[]);self.assertTrue(b.state['allIdentified'])
        self.assertEqual(b.state['recommendedCells'],[])
        self.assertEqual(b.state['probabilities'],[None]*25)
        self.assertEqual(b.overlay_window.publish.call_args.args[0]['probabilities'],[None]*25)
        self.assertIn(20,b.state['markedTreasure']);self.assertNotIn(10,b.state['markedTreasure'])

    def test_hit_first_enumeration_matches_independent_exhaustive_layouts(self):
        from itertools import product
        mask=np.ones((64,32),np.uint8);templates=[{'mask':mask},{'mask':mask}]
        cells=[2,0,0,0,0,0,0,0,0];foreground=np.zeros((96,96),np.uint8)
        choices=[options_for(3,t,cells,foreground) for t in templates]
        layouts=[a['mask']|b['mask'] for a,b in product(*choices) if not a['mask']&b['mask'] and (a['mask']|b['mask'])&1]
        result=infer(3,templates,cells,foreground)
        self.assertTrue(result['exact']);self.assertEqual(result['count'],len(layouts))
        for i,p in enumerate(result['probabilities']):self.assertAlmostEqual(p,sum(bool(m>>i&1) for m in layouts)/len(layouts))

    def test_single_exposed_piece_does_not_mark_arbitrary_neighbor_square(self):
        frame=cv2.imread(str(ROOT/'tests/fixtures/treasure/stage2-single-hit.png'))
        obs=observe(frame);b=TreasureBackend(discover=False);b.calculate=lambda:None;b.applyObservation(frame,obs,2)
        result=infer(5,b.templates,b.state['cells'],obs.foreground)
        self.assertEqual([i for i,v in enumerate(obs.cells) if v==2],[6])
        self.assertFalse(result['ghosts'])
        self.assertTrue(result['candidateGhosts'])
        self.assertLess(max(g['support'] for g in result['candidateGhosts']),.9)

    def test_same_count_different_silhouettes_reconfigure_even_after_previous_board(self):
        b=TreasureBackend(discover=False);b.calculate=lambda:None
        for name,expected in [('stage2-single-hit.png',[[2,2,1],[1,2,3]]),('stage2-alternate-shapes.png',[[1,2,2],[1,3,2]])]:
            frame=cv2.imread(str(ROOT/'tests/fixtures/treasure'/name));obs=observe(frame)
            b.applyObservation(frame,obs,2)
            self.assertEqual(b.state['shapes'],expected)
            if 'alternate' in name:self.assertTrue(b.state['configurationWarning'])


class CandidateDisplayTests(unittest.TestCase):
    def test_weak_location_remains_visible_without_becoming_confirmed_or_stopping(self):
        frame=cv2.imread(str(ROOT/'tests/fixtures/treasure/stage2-single-hit.png'))
        obs=observe(frame);b=TreasureBackend(discover=False);b.calculate=lambda:None;b.applyObservation(frame,obs,2)
        result=infer(5,b.templates,b.state['cells'],obs.foreground)
        result['estimate']={'cost':200,'cells':13};result['guided']={'cost':150,'cells':10}
        b.finish(b.revision,result)
        self.assertTrue(b.state['candidateTreasure'])
        self.assertIn(6,b.state['markedTreasure']);self.assertTrue(set(b.state['candidateTreasure']).issubset(b.state['markedTreasure']));self.assertFalse(b.state['allLocated'])
        self.assertEqual(b.state['pendingShapes'],b.state['shapes'])
        self.assertEqual(b.state['probabilities'],result['probabilities'])
        index=next(i for i in b.state['candidateTreasure'] if i!=6)
        b.mark(index,0);b.finish(b.revision,result)
        self.assertFalse(b.state['candidateTreasure'])
        b.undo();b.finish(b.revision,result);self.assertTrue(b.state['candidateTreasure'])


class IdentifiedAndCompletedRegressionTests(unittest.TestCase):
    def observation(self,name):
        from treasure.vision import Observation
        frame=cv2.imread(str(ROOT/'tests/fixtures/treasure'/name))
        hint=Observation((139,460,262,270),5,[],None,[],np.zeros((160,160),np.uint8),frame.shape[:2])
        return frame,observe(frame,hint)

    def test_recognized_book_is_not_pending_when_footprint_was_uncertain(self):
        from treasure.presentation import pending_identified
        for name in ('stage2-book-identified.png','stage2-multiple-identified.png'):
            frame,obs=self.observation(name);b=TreasureBackend(discover=False);b.calculate=lambda:None;b.applyObservation(frame,obs,2)
            result=infer(5,b.templates,b.state['cells'],obs.foreground)
            pending=pending_identified(b.state['shapes'],result['identifiedShapes'])
            self.assertNotIn([2,2,1],pending)
            self.assertIn([2,2,1],result['identifiedShapes'])

    def test_colored_completed_item_deducted_once_and_remaining_identities_recognized(self):
        from treasure.presentation import pending_identified
        frame,obs=self.observation('stage2-colored-complete.png')
        self.assertEqual(sum(s['completed'] for s in obs.silhouettes),1)
        b=TreasureBackend(discover=False);b.calculate=lambda:None;b.applyObservation(frame,obs,2)
        self.assertEqual(b.completed_count,1);self.assertEqual(b.state['shapes'],[[1,2,2],[2,2,1]])
        result=infer(5,b.templates,b.state['cells'],obs.foreground)
        self.assertEqual(pending_identified(b.state['shapes'],result['identifiedShapes']),[])
        b.applyObservation(frame,obs,2);self.assertEqual(b.state['shapes'],[[1,2,2],[2,2,1]])
        from treasure.vision import read_tray
        dark=frame.copy();x,y,w,h=obs.tray
        item=next(s for s in obs.silhouettes if s['completed']);a,c,iw,ih=item['box']
        hsv=cv2.cvtColor(dark[y+c:y+c+ih,x+a:x+a+iw],cv2.COLOR_BGR2HSV)
        selected=(hsv[:,:,1]>70)&(hsv[:,:,2]>90);hsv[:,:,2][selected]=120
        dark[y+c:y+c+ih,x+a:x+a+iw]=cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR)
        _,shapes=read_tray(dark,obs.rect)
        self.assertEqual(sum(s['completed'] for s in shapes),1)
