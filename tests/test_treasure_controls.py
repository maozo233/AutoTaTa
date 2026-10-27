import unittest
from unittest.mock import Mock,patch
from treasure.backend import TreasureBackend

class TreasureControlsTests(unittest.TestCase):
    def setUp(self):
        self.b=TreasureBackend(discover=False)
        self.b.calculate=Mock()
    def test_edit_add_remove_undo_and_capacity(self):
        b=self.b
        self.assertTrue(b.editTreasure(-1,2,2,1))
        self.assertEqual(b.state['shapes'][-1],[2,2,1])
        before=b.state['shapes']
        self.assertFalse(b.changeQuantity(1,10))
        self.assertEqual(b.state['shapes'],before)
        self.assertTrue(b.changeQuantity(1,-1))
        self.assertEqual(len(b.state['shapes']),1)
        b.undo();self.assertEqual(b.state['shapes'],before)

    def test_stage_undo_restores_auto_configuration_and_dismissed_predictions(self):
        b=self.b;b.live['autoConfig']=True;b.dismissed_predictions={3,8}
        before=b.state['stage']
        b.selectStage(2)
        self.assertFalse(b.live['autoConfig']);self.assertEqual(b.dismissed_predictions,set())
        b.undo()
        self.assertEqual(b.state['stage'],before)
        self.assertTrue(b.live['autoConfig']);self.assertEqual(b.dismissed_predictions,{3,8})

    def test_clear_undo_restores_located_state_and_cell_markings(self):
        b=self.b;b._state['allLocated']=True;b._state['cells'][3]=2
        b.clear()
        self.assertFalse(b._state['allLocated']);self.assertEqual(b.state['cells'][3],0)
        b.undo()
        self.assertTrue(b._state['allLocated']);self.assertEqual(b.state['cells'][3],2)
    def test_manual_cell_is_not_inferred_opened_cell(self):
        b=self.b;b._state['certainTreasure']=[2]
        b.mark(0,2)
        self.assertEqual(b.state['cells'][2],0)
        self.assertEqual(b.state['cells'][0],2)
        b.undo();self.assertEqual(b.state['cells'][0],0)
    def test_continuous_updates_until_manual_stop(self):
        b=self.b;b.live['running']=True;b.watcher=Mock();b.overlay_window=Mock()
        b.applyObservation=Mock(return_value=True)
        b.acceptObservation(b.generation,None,None,None)
        self.assertTrue(b.live['running']);self.assertTrue(b.snapshot_ready)
        b.boardSeen(b.generation);b.overlay_window.heartbeat.assert_called()
        b.overlay_window.reset_mock()
        b.boardChanged(b.generation)
        self.assertFalse(b.snapshot_ready);b.overlay_window.publish.assert_not_called();b.overlay_window.setEnabled.assert_not_called()
        b.acceptObservation(b.generation,None,None,None)
        self.assertEqual(b.applyObservation.call_count,2)
        self.assertTrue(b.live['running']);self.assertTrue(b.snapshot_ready)
        old=b.generation;watcher=b.watcher;b.stopWatch()
        watcher.stop.assert_called_once();self.assertFalse(b.live['running'])
        b.acceptObservation(old,None,None,None)
        self.assertEqual(b.applyObservation.call_count,2)

    def test_old_session_cannot_update_after_device_change(self):
        b=self.b;b.devices=[{'hwnd':1},{'hwnd':2}];b.watcher=Mock();old=b.generation
        b.chooseDevice(1)
        self.assertIsNone(b.watcher);self.assertNotEqual(b.generation,old)
        b.applyObservation=Mock();b.live['running']=True
        b.acceptObservation(old,None,None,None);b.applyObservation.assert_not_called()

    def test_located_neighbor_marked_without_probability_boost(self):
        from treasure.presentation import markers_and_recommendations
        cells=[0]*25
        for i in [5,6,12,20]:cells[i]=1
        cells[16]=2
        probs=[.17,.31,.39,.36,.31,0,0,.27,.46,.43,.27,.24,0,.34,.39,.29,1,.39,.41,.37,0,.63,.32,.36,.27]
        before=probs[:]
        marked,recommended=markers_and_recommendations(cells,probs,[],[16,21])
        self.assertEqual(marked,[16,21]);self.assertEqual(recommended,[8])
        self.assertEqual(cells[21],0);self.assertEqual(probs,before)

    def test_no_recommendation_when_only_located_cells_remain(self):
        from treasure.presentation import markers_and_recommendations
        self.assertEqual(markers_and_recommendations([0,0],[.8,1],[],[0,1]),([0,1],[]))

    def test_disconnect_retries_without_turning_off_switch(self):
        b=self.b;b.retry_timer=Mock();b.live['running']=True;b.watcher=Mock();b.overlay_window=Mock()
        b.watchStopped(b.generation)
        self.assertTrue(b.live['running']);self.assertIsNone(b.watcher)
        b.retry_timer.start.assert_called_once()
        b.stopWatch();b.retry_timer.stop.assert_called_once()
        self.assertFalse(b.live['running'])

    def test_no_device_keeps_waiting_until_manual_stop(self):
        b=self.b;b.retry_timer=Mock();b.devices=[];b.refreshDevices=Mock()
        b.startWatch()
        self.assertTrue(b.live['running']);b.retry_timer.start.assert_called_once()
        b.stopWatch();self.assertFalse(b.live['running'])

    def test_status_distinguishes_wait_ready_error_and_stop(self):
        from treasure.presentation import recognition_status
        live={'running':True,'status':'已识别 5×5'}
        self.assertEqual(recognition_status(live,True)['label'],'识别正常')
        self.assertEqual(recognition_status(live,False)['label'],'等待识别')
        self.assertEqual(recognition_status(live,True,'尺寸待核对')['label'],'待校正')
        live['status']='连接中断，正在重新连接…'
        self.assertEqual(recognition_status(live,False)['label'],'连接异常')
        live['running']=False
        self.assertEqual(recognition_status(live,False)['label'],'已停止')

    def test_configuration_warning_is_visible_and_manual_edit_clears_it(self):
        b=self.b;b.live['configurationWarning']='宝物识别不完整，请修改尺寸与数量'
        self.assertIn('识别不完整',b.state['configurationWarning'])
        self.assertTrue(b.editTreasure(0,1,3,2))
        self.assertEqual(b.state['configurationWarning'],'')
        b._state['status']='计算失败：无可行布局'
        self.assertIn('标记不匹配',b.state['configurationWarning'])

    def test_board_warning_missing_and_recovery(self):
        import cv2
        from treasure.vision import observe
        b=self.b;b.live['running']=True
        b.watchStatus(b.generation,'未找到稳定棋盘，请进入营地寻宝')
        self.assertIn('未找到',b.state['boardWarning'])
        b.watchStatus(b.generation-1,'正在连接')
        self.assertIn('未找到',b.state['boardWarning'])
        frame=cv2.imread('tests/fixtures/treasure/live-stage1.png')
        obs=observe(frame);b.applyObservation(frame,obs,1)
        self.assertEqual(b.state['boardWarning'],'')

    def test_unknown_tiles_warn_until_corrected(self):
        import cv2
        from treasure.vision import observe
        b=self.b;frame=cv2.imread('tests/fixtures/treasure/live-stage1.png')
        obs=observe(frame);obs.cells[0]=-1
        b.applyObservation(frame,obs,1)
        self.assertIn('1 个格子',b.state['boardWarning'])
        b.mark(0,1);self.assertEqual(b.state['boardWarning'],'')
        b.undo();self.assertIn('1 个格子',b.state['boardWarning'])
        obs.cells[0]=0;b.applyObservation(frame,obs,1)
        self.assertEqual(b.state['boardWarning'],'')

    def test_board_warning_for_size_mismatch_and_conflicting_marks(self):
        import cv2
        from treasure.vision import observe
        b=self.b;b.configure(6,15,'1x2:1')
        frame=cv2.imread('tests/fixtures/treasure/live-stage1.png')
        self.assertFalse(b.applyObservation(frame,observe(frame),None))
        self.assertIn('尺寸',b.state['boardWarning'])
        b.configure(5,15,'1x2:1');self.assertEqual(b.state['boardWarning'],'')
        b._state['status']='没有符合标记的布局'
        self.assertIn('不匹配',b.state['boardWarning'])

    def test_same_stage_new_board_resets_manual_marks_and_completed_state(self):
        import cv2
        from treasure.vision import observe
        b=self.b;frame=cv2.imread('tests/fixtures/treasure/stage1-three-treasures.png');obs=observe(frame)
        b.applyObservation(frame,obs,1);b.clear();b.completed_count=1
        self.assertEqual(b.state['cells'],[0]*25)
        b.applyObservation(frame,obs,{'stage':1,'cost':15,'newSession':True})
        self.assertEqual(b.state['cells'],obs.cells)
        self.assertEqual([i for i,v in enumerate(b.state['cells']) if v==1],[0,6,12,18])
        self.assertEqual(b.completed_count,0);self.assertFalse(b.overrides);self.assertFalse(b.history)

    def test_new_covered_board_confirmed_automatically_but_single_frame_retained(self):
        import cv2,copy
        from treasure.vision import observe
        b=self.b;frame=cv2.imread('tests/fixtures/treasure/stage1-three-treasures.png');old=observe(frame)
        b.applyObservation(frame,old,1);new=copy.deepcopy(old);new.cells=[0]*25
        self.assertFalse(b.applyObservation(frame,new,1))
        self.assertEqual(b.state['cells'],old.cells)
        b.applyObservation(frame,old,1)
        self.assertFalse(b.applyObservation(frame,new,1))
        b.applyObservation(frame,new,1)
        self.assertEqual(b.state['cells'],[0]*25);self.assertFalse(b.state['boardWarning'])
        self.assertNotIn('重新进入',b.state['live']['status'])

    def test_partial_new_board_replaces_old_opened_tiles(self):
        import cv2,copy
        from treasure.vision import observe
        b=self.b;frame=cv2.imread('tests/fixtures/treasure/stage1-three-treasures.png');old=observe(frame)
        b.applyObservation(frame,old,1);new=copy.deepcopy(old);new.cells=[0]*25;new.cells[3]=1
        b.applyObservation(frame,new,1);b.applyObservation(frame,new,1)
        self.assertEqual(b.state['cells'],new.cells)

    def test_pending_treasures_count_complete_rectangles_not_original_configuration(self):
        from treasure.presentation import located_progress
        progress=located_progress(5,[[2,2,1],[1,2,3]],[0]*25,[0,1,5,6,10,11])
        self.assertEqual(progress['pendingShapes'],[[1,2,2]])
        self.assertFalse(progress['complete'])
        complete=located_progress(5,[[2,2,1],[1,2,3]],[0]*25,[0,1,5,6,10,11,15,16,20,21])
        self.assertTrue(complete['complete']);self.assertEqual(complete['pendingShapes'],[])
        self.assertEqual(complete['remainingDigCells'],10)
        # Same area scattered across incompatible placements does not mean complete.
        self.assertFalse(located_progress(5,[[2,2,1]],[0]*25,[0,2,10,12])['complete'])
        self.assertFalse(located_progress(5,[[1,2,1]],[0]*25,[0,1,2])['complete'])

    def test_fully_located_board_stops_solver_but_updates_cost_and_can_resume(self):
        from unittest.mock import patch
        from treasure.backend import TreasureBackend
        b=TreasureBackend(discover=False);b._state.update(size=5,shapes=[[1,2,1]],cells=[0]*25,allLocated=True,locatedCells=[0,1])
        with patch('treasure.backend.solve') as solve:
            b.calculate();solve.assert_not_called()
            self.assertEqual(b.state['recommendedCells'],[])
            self.assertIn('30',b.state['estimatePrimary'])
            b._state['cells'][0]=2;b.calculate();solve.assert_not_called()
            self.assertIn('15',b.state['estimatePrimary'])
            b._state['cells'][0]=1;b.calculate()
            self.assertFalse(b.state['allLocated'])

    def test_restore_unopened_dismisses_prediction_and_undo_restores_it(self):
        from treasure.presentation import trusted_ghosts
        b=self.b;b._state.update(predictedTreasure=[0,1],markedTreasure=[0,1])
        ghost={'x':0,'y':0,'w':2,'h':1,'support':.95,'certain':False,'pinned':False}
        b.mark(0,0)
        self.assertIn(0,b.state['dismissedPredictions'])
        self.assertEqual(trusted_ghosts([ghost],b.dismissed_predictions,5),[])
        b.undo();self.assertEqual(b.state['dismissedPredictions'],[])
        self.assertEqual(trusted_ghosts([ghost],b.dismissed_predictions,5),[ghost])

    def test_explore_outside_weak_footprint_before_completing_it(self):
        from treasure.presentation import markers_and_recommendations
        marked,recommended=markers_and_recommendations([0,0,2],[.6,.9,1],[],[1,2],[1])
        self.assertEqual(recommended,[0]);self.assertEqual(marked,[1,2])
        _,recommended=markers_and_recommendations([1,0,2],[0,.9,1],[],[1,2],[1])
        self.assertEqual(recommended,[1])

    def test_all_identities_known_do_not_recommend_other_cells(self):
        from treasure.presentation import markers_and_recommendations
        _,recommended=markers_and_recommendations([0,0,2],[.9,.6,1],[],[1,2],[1],True)
        self.assertEqual(recommended,[])

    def test_confirm_keeps_capture_and_evidence_and_acknowledges_estimated_sizes(self):
        b=self.b;b.live.update(running=True,derived=True,configurationWarning='宝物尺寸为估算，请核对尺寸与数量')
        b._state['cells'][0]=2;b._state['treasureHistory']=[0];b.templates=[{'sentinel':True}]
        self.assertTrue(b.confirmTreasures())
        self.assertTrue(b.state['treasuresConfirmed']);self.assertFalse(b.state['configurationWarning'])
        self.assertTrue(b.live['running']);self.assertTrue(b.live['autoConfig'])
        self.assertEqual(b.state['cells'][0],2);self.assertEqual(b.templates,[{'sentinel':True}])
        b._state['shapes']=[[1,3,2]];self.assertTrue(b.state['treasuresConfirmed'])
        b.selectStage(2,internal=True);self.assertFalse(b.state['treasuresConfirmed'])
    def test_edit_requires_confirmation_again_and_invalid_capacity_is_rejected(self):
        b=self.b;self.assertTrue(b.confirmTreasures());self.assertTrue(b.editTreasure(-1,1,1,1))
        self.assertFalse(b.state['treasuresConfirmed'])
        b._state['shapes']=[[5,5,2]];self.assertFalse(b.confirmTreasures())
        self.assertIn('无效',b.state['configurationWarning'])
