"""Public-catalog integrity, supplied screenshots, and device-free deployments."""
import hashlib,json,threading,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from pathlib import Path
import cv2,numpy as np
from PIL import Image
from lineup.catalog import load_catalog,choose_available,deployment_plan
from lineup.vision import Vision,Grid,Observation,read_image,grayscale_grid,card_reference_grid,checker_reference_grid,import_formation
from lineup.engine import execute,project_cells
from lineup.input import drag
from autotata.paths import ASSETS

FIXTURES=Path(__file__).parent/'fixtures/lineup'


class CatalogTests(unittest.TestCase):
    def test_catalog_preserves_all_source_records_and_stage_chains(self):
        items=load_catalog();self.assertEqual(len(items),248)
        self.assertEqual(len({r['family'] for r in items}),67)
        previous=None
        for row in items:
            if row['stage']==1:self.assertEqual(row['family'],row['id'])
            else:
                self.assertEqual(row['stage'],previous['stage']+1)
                self.assertEqual((row['family'],row['elementKey'],row['roleKey']),
                    (previous['family'],previous['elementKey'],previous['roleKey']))
            self.assertTrue(row['name']);self.assertTrue(row['role']);self.assertTrue(row['element'])
            previous=row
    def test_png_alpha_and_source_hashes(self):
        for row in load_catalog():
            path=ASSETS/row['imagePath']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),row['sha256'])
            with Image.open(path) as im:
                self.assertEqual(im.format,'PNG')
                lo,hi=im.convert('RGBA').getchannel('A').getextrema()
                self.assertEqual(lo,0);self.assertGreaterEqual(hi,127)
    def test_substitution_prefers_exact_then_highest_same_family(self):
        self.assertEqual(choose_available('manteeny',[{'id':'serrabloom'},{'id':'manteeny'}])['id'],'manteeny')
        self.assertEqual(choose_available('manteeny',[{'id':'stalkerix'},{'id':'serrabloom'},{'id':'dozy'}])['id'],'serrabloom')
        self.assertIsNone(choose_available('manteeny',[{'id':'dozy'}]))
    def test_plan_partial_unknown_missing_duplicate_and_limit(self):
        r=deployment_plan(['?', 'manteeny','dozy','manteeny','rockwu'],[{'id':'serrabloom'},{'id':'dozy'},{'id':'rockwu'}],2)
        self.assertEqual([p['actual'] for p in r['placements']],['serrabloom','dozy'])
        self.assertEqual([i['reason'] for i in r['issues']],['识别不确定','库存未找到','超过上阵上限'])
    def test_center_projection_keeps_edge_issues(self):
        cells=[None]*25;cells[5]='dozy';cells[6]='rockwu';cells[8]='manteeny'
        projected,issues=project_cells(cells,5,3)
        self.assertEqual(projected[3],'rockwu');self.assertEqual(projected[5],'manteeny')
        self.assertEqual(issues,[{'sourceIndex':5,'reason':'超出当前场地'}])


class ScreenshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cv2.setNumThreads(1);cls.vision=Vision()
    def test_two_deployment_boards_and_no_concatenated_inventory_digits(self):
        for name,columns,limit,rect in [('formation-five',3,5,(185,329,170,228)),('formation-fifteen',5,15,(120,255,300,300))]:
            obs=self.vision.observe(read_image(FIXTURES/(name+'.png')))
            self.assertEqual((obs.state,obs.count,obs.limit,obs.grid.columns),('ready',0,limit,columns))
            self.assertGreaterEqual(len(obs.cards),6)
            self.assertLess(max(abs(a-b) for a,b in zip(obs.grid.rect,rect)),10)
            self.assertTrue(obs.clear[0]>450)
    def test_stacked_right_controls_do_not_hide_count_or_move_player_grid(self):
        frame=read_image(FIXTURES/'live-stacked-controls.png');v=Vision();obs=v.observe(frame)
        self.assertEqual((obs.state,obs.count,obs.limit),('ready',15,15))
        self.assertEqual(len(obs.cards),10)
        self.assertEqual(set(obs.filters),{'all','water','fire','grass','rock','lightning'})
        self.assertGreater(obs.count_y-obs.clear[1],100*obs.scale)
        self.assertLess(max(abs(a-b) for a,b in zip(obs.grid.rect,(120,260,300,300))),10)
        # Supplying the same verified grid also keeps fresh-frame input guards
        # on the field when the clear icon is a full row above the count bar.
        anchored=v.observe(frame,grid_hint=(obs.grid,obs.clear,obs.limit,obs.count_y))
        self.assertEqual(anchored.grid.rect,obs.grid.rect)
    def test_grid_detection_unchanged_with_gray_input(self):
        original=read_image(FIXTURES/'reference-grid.png')
        gray=cv2.cvtColor(cv2.cvtColor(original,cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
        self.assertEqual(grayscale_grid(original).rect,grayscale_grid(gray).rect)
        self.assertEqual(grayscale_grid(original).columns,5)
    def test_borderless_checker_reference_keeps_all_fifteen_cells_after_scaling_and_compression(self):
        image=read_image(FIXTURES/'formation-borderless.png')
        expected=[None,None,'pyrohound','clawzor','cobbledon','sizribb','blitzmane','firecoil','cheerlet','turtuff',
                  'pyroprawn',None,None,'zapooch',None,None,None,None,None,None,'bubbit','sparkdoe','azurion','frostique','rattlecoil']
        compressed=cv2.imdecode(cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,90])[1],cv2.IMREAD_COLOR)
        for label,frame in [('original',image),('scaled',cv2.resize(image,None,fx=1.4,fy=1.4)),('jpeg',compressed)]:
            with self.subTest(label=label):
                result=import_formation(frame)
                self.assertEqual(result['cells'],expected)
    def test_borderless_geometry_uses_grayscale_and_does_not_invent_uniform_or_gradient_grids(self):
        image=read_image(FIXTURES/'formation-borderless.png')
        gray=cv2.cvtColor(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
        self.assertEqual(checker_reference_grid(image).rect,checker_reference_grid(gray).rect)
        for frame in (np.full_like(image,220),np.repeat(np.tile(np.linspace(80,220,image.shape[1],dtype=np.uint8),(image.shape[0],1))[:,:,None],3,axis=2)):
            self.assertIsNone(checker_reference_grid(frame))
    def test_borderless_detector_checks_cancel_before_phase_search(self):
        cancelled=threading.Event();cancelled.set()
        with self.assertRaisesRegex(RuntimeError,'停止'):
            checker_reference_grid(read_image(FIXTURES/'formation-borderless.png'),cancel=cancelled)
    def test_unchanged_count_strip_skips_repeated_ocr_but_new_count_is_read(self):
        v=Vision();empty=read_image(FIXTURES/'live-empty-inventory.png');deployed=read_image(FIXTURES/'live-deployed.png')
        with patch.object(v,'text',wraps=v.text) as ocr:
            self.assertEqual(v.observe(empty).count,0)
            animated=empty.copy();animated[250:350,200:600]=200
            self.assertEqual(v.observe(animated).count,0)
            self.assertEqual(ocr.call_count,1)
            self.assertEqual(v.observe(deployed).count,6)
            self.assertEqual(ocr.call_count,2)
    def test_deployed_portraits_do_not_move_the_grid(self):
        frame=read_image(FIXTURES/'formation-fifteen.png');before=self.vision.observe(frame)
        char=cv2.resize(read_image(ASSETS/'lineup/tatari/serrabloom.png'),(42,42));alpha=char[:,:,3:]/255
        for index in (0,1,2,3,4,6,7,8,11,12,13,16,17,18,22):
            x,y=map(round,before.grid.center(index));roi=frame[y-21:y+21,x-21:x+21]
            roi[:]=(roi*(1-alpha)+char[:,:,:3]*alpha).astype(np.uint8)
        after=self.vision.observe(frame)
        self.assertLess(max(abs(a-b) for a,b in zip(before.grid.rect,after.grid.rect)),3)
    def test_card_border_formation(self):
        grid=card_reference_grid(read_image(FIXTURES/'reference-cards.png'))
        self.assertIsNotNone(grid);self.assertEqual((grid.columns,grid.rows),(5,5))
        self.assertLess(np.linalg.norm(np.subtract(grid.center(0),(69,84))),8)
    def test_battle_reference_cannot_be_bound_as_deployment(self):
        self.assertEqual(self.vision.observe(read_image(FIXTURES/'reference-game.png')).state,'unknown')
    def test_invalid_crop_never_selects_a_display(self):
        image=read_image(FIXTURES/'formation-fifteen.png')
        self.assertEqual(Vision(2000,0).observe(image).state,'unknown')
        self.assertEqual(Vision(500,500).observe(image).state,'unknown')
    def test_large_manual_crop_keeps_original_coordinates(self):
        frame=np.full((1500,1500,3),240,np.uint8)
        result=import_formation(frame,manual_rect=(150,200,1000,1000))
        self.assertEqual(result['grid'].rect,(150,200,1000,1000))
        self.assertEqual(result['cells'],[None]*25)
    def test_reference_grid_has_fifteen_units_and_known_samples(self):
        result=import_formation(read_image(FIXTURES/'reference-grid.png'))
        self.assertEqual(sum(k is not None for k in result['cells']),15)
        self.assertEqual(result['cells'][7],'blitzmane')
        self.assertEqual(result['cells'][10],'rockshell')
        self.assertEqual(result['cells'][21],'bubbit')
        self.assertEqual(result['cells'][:5],[None]*5)
    def test_empty_and_cancelled_images_never_infer_units(self):
        result=import_formation(np.full((250,250,3),240,np.uint8),manual_rect=(0,0,250,250))
        self.assertEqual(result['cells'],[None]*25)
        event=threading.Event();event.set()
        with self.assertRaisesRegex(RuntimeError,'停止'):
            import_formation(np.zeros((250,250,3),np.uint8),manual_rect=(0,0,250,250),cancel=event)


class FakeOperations:
    def __init__(self,board=None,inventory=None,limit=15):
        self.units=dict(board or {});self.limit=limit;self.calls=[]
        self.inventory=inventory if inventory is not None else [{'id':'dozy'},{'id':'serrabloom'}]
    @property
    def count(self):return len(self.units)
    def snapshot(self):return Observation(state='ready',count=self.count,limit=self.limit,grid=Grid((0,0,250,250),5,5))
    def board(self):return [{'index':i,'id':k} for i,k in self.units.items()]
    def wait_count(self,count):assert self.count==count;return self.snapshot()
    def wait_move(self,count):assert self.count==count;return self.snapshot()
    def withdraw(self,index,count):
        assert count==self.count;self.calls.append(('withdraw',index));self.inventory.append({'id':self.units.pop(index)})
    def withdraw_unrecognized(self,index,count):self.withdraw(index,count)
    def move(self,source,target,count):
        assert count==self.count and target not in self.units
        self.calls.append(('move',source,target));self.units[target]=self.units.pop(source)
    def find_available(self,identity,used):
        self.calls.append(('find',identity));return choose_available(identity,self.inventory,used)
    def deploy(self,card,target,count,index):
        assert index not in self.units and count==self.count and count<self.limit
        self.calls.append(('drag',card['id'],index));self.units[index]=card['id'];self.inventory.remove(card)


class DeploymentTests(unittest.TestCase):
    def test_find_and_deploy_are_interleaved_without_bulk_scan(self):
        ops=FakeOperations();events=[]
        plan=execute(ops,['dozy','manteeny','?']+[None]*22,5,events.append)
        self.assertEqual(ops.calls,[('find','dozy'),('drag','dozy',0),('find','manteeny'),('drag','serrabloom',1)])
        self.assertTrue(plan['placements'][1]['substituted']);self.assertEqual(events[-1]['completed'],2)
    def test_matching_deployed_units_move_before_inventory_search(self):
        ops=FakeOperations({4:'dozy',5:'rockwu'},[{'id':'serrabloom'}])
        execute(ops,['dozy','manteeny']+[None]*23,5,lambda e:None)
        self.assertEqual(ops.calls,[('move',4,0),('withdraw',5),('find','manteeny'),('drag','serrabloom',1)])
        self.assertEqual(ops.units,{0:'dozy',1:'serrabloom'})
    def test_correctly_positioned_units_are_not_touched(self):
        ops=FakeOperations({0:'dozy'},[]);execute(ops,['dozy']+[None]*24,5,lambda e:None)
        self.assertEqual(ops.calls,[])
    def test_cycle_uses_empty_cell_without_withdrawing_matches(self):
        ops=FakeOperations({0:'dozy',1:'serrabloom'},[])
        execute(ops,['manteeny','dozy']+[None]*23,5,lambda e:None)
        self.assertEqual(ops.units,{0:'serrabloom',1:'dozy'})
        self.assertEqual(len(ops.calls),3);self.assertTrue(all(c[0]=='move' for c in ops.calls))
    def test_blocker_is_withdrawn_before_retained_drag(self):
        ops=FakeOperations({0:'rockwu',4:'dozy'},[])
        execute(ops,['dozy']+[None]*24,5,lambda e:None)
        self.assertEqual(ops.calls,[('withdraw',0),('move',4,0)])
    def test_unknown_deployed_unit_is_withdrawn_and_target_completed(self):
        ops=FakeOperations({0:'?',4:'dozy'},[])
        plan=execute(ops,['dozy']+[None]*24,5,lambda e:None)
        self.assertEqual(ops.calls,[('withdraw',0),('move',4,0)]);self.assertEqual(ops.units,{0:'dozy'});self.assertEqual(plan['issues'],[])
    def test_unknown_blocker_does_not_create_infinite_movement_cycle(self):
        ops=FakeOperations({0:'?',1:'dozy',2:'serrabloom'},[])
        plan=execute(ops,['dozy','manteeny']+[None]*23,5,lambda e:None)
        self.assertLess(len(ops.calls),5);self.assertEqual(plan['issues'],[])
    def test_exact_match_reserved_before_same_family_fallback(self):
        ops=FakeOperations({3:'serrabloom',4:'manteeny'},[])
        plan=execute(ops,['manteeny','serrabloom']+[None]*23,5,lambda e:None)
        self.assertEqual([p['actual'] for p in plan['placements']],['manteeny','serrabloom'])
    def test_no_confirmed_targets_preserves_current_team(self):
        ops=FakeOperations({0:'dozy'});execute(ops,['?']+[None]*24,5,lambda e:None)
        self.assertEqual(ops.calls,[]);self.assertEqual(ops.count,1)
    def test_missing_unit_does_not_block_other_targets(self):
        ops=FakeOperations(inventory=[{'id':'serrabloom'}])
        plan=execute(ops,['dozy','manteeny']+[None]*23,5,lambda e:None)
        self.assertEqual(ops.count,1);self.assertEqual(plan['issues'][0]['reason'],'库存未找到')
    def test_failed_withdraw_never_adds_at_full_capacity(self):
        ops=FakeOperations({0:'rockwu'},limit=1);ops.withdraw=lambda i,c:None
        with self.assertRaises(AssertionError):execute(ops,['dozy']+[None]*24,5,lambda e:None)
        self.assertFalse(any(c[0]=='drag' for c in ops.calls))
    def test_limit_change_during_inventory_search_stops_drag(self):
        ops=FakeOperations();old=ops.find_available
        def find(k,used):ops.limit=1;return old(k,used)
        ops.find_available=find
        with self.assertRaisesRegex(RuntimeError,'变化'):execute(ops,['dozy']+[None]*24,5,lambda e:None)
        self.assertFalse(any(c[0]=='drag' for c in ops.calls))
    def test_deployed_count_mismatch_sends_no_input(self):
        ops=FakeOperations({0:'dozy'});ops.board=lambda:[]
        with self.assertRaisesRegex(RuntimeError,'数量不一致'):execute(ops,['dozy']+[None]*24,5,lambda e:None)
        self.assertEqual(ops.calls,[])
    def test_full_capacity_withdraws_mismatch_before_finding_replacement(self):
        ops=FakeOperations({0:'rockwu',1:'dozy'},[{'id':'serrabloom'}],limit=2)
        execute(ops,['manteeny','dozy']+[None]*23,5,lambda e:None)
        self.assertEqual(ops.calls,[('withdraw',0),('find','manteeny'),('drag','serrabloom',0)])


class DragTests(unittest.TestCase):
    def test_sdk_capture_mode_binds_native_touch_for_lineup_only(self):
        from lineup.runner import connect
        from lineup.engine import Settings
        cancel=threading.Event()
        with patch('fishing.adb_session.AdbSession') as session:
            capture,mouse=connect(123,Settings(mode='mumu_sdk'),cancel)
        session.assert_called_once()
        self.assertEqual(session.call_args.kwargs['mode'],'maatouch')
        self.assertTrue(session.call_args.kwargs['allow_active'])
        self.assertIs(capture,mouse);mouse.start.assert_called_once()
    def setup_session(self):
        done=SimpleNamespace(done=True,succeeded=True)
        controller=Mock();controller.post_touch_down.return_value=done;controller.post_touch_move.return_value=done;controller.post_touch_up.return_value=done;controller.post_inactive.return_value=done
        session=SimpleNamespace(size=(300,600),controller=controller,validate=Mock(return_value=True))
        cancel=Mock();cancel.is_set.return_value=False;cancel.wait.return_value=False
        return session,cancel,controller
    def test_drag_releases_one_contact(self):
        session,cancel,c=self.setup_session();drag(session,(100,500),(150,150),cancel)
        c.post_touch_down.assert_called_once_with(100,500,contact=0)
        self.assertGreaterEqual(c.post_touch_move.call_count,12);self.assertLessEqual(c.post_touch_move.call_count,20)
        c.post_touch_up.assert_called_once_with(contact=0)
        c.post_touch_move.assert_called_with(150,150,contact=0)
    def test_inventory_drag_lifts_vertically_before_crossing_board(self):
        session,cancel,c=self.setup_session()
        drag(session,(60,500),(240,150),cancel,waypoint=(60,350))
        points=[call.args for call in c.post_touch_move.call_args_list]
        self.assertLessEqual(abs(points[0][1]-500),12)
        lift=points.index((60,350))
        self.assertTrue(all(x==60 for x,y in points[:lift+1]))
        self.assertEqual(points[-1],(240,150))
        c.post_touch_down.assert_called_once_with(60,500,contact=0)
        c.post_touch_up.assert_called_once_with(contact=0)
        self.assertLess(cancel.wait.call_args_list[0].args[0],.1)
    def test_invalid_waypoint_never_presses(self):
        session,cancel,c=self.setup_session()
        with self.assertRaisesRegex(RuntimeError,'超出'):drag(session,(60,500),(240,150),cancel,waypoint=(600,350))
        c.post_touch_down.assert_not_called()
    def test_cancel_mid_drag_always_releases(self):
        session,cancel,c=self.setup_session();cancel.wait.return_value=True
        with self.assertRaisesRegex(RuntimeError,'停止'):drag(session,(100,500),(150,150),cancel)
        c.post_touch_up.assert_called_once();c.post_touch_move.assert_not_called()
    def test_failed_down_does_not_send_invalid_up_or_mask_error(self):
        session,cancel,c=self.setup_session();c.post_touch_down.side_effect=RuntimeError('按下失败')
        with self.assertRaisesRegex(RuntimeError,'按下失败'):drag(session,(100,500),(150,150),cancel)
        c.post_touch_up.assert_not_called();c.post_inactive.assert_called_once()
    def test_out_of_bounds_and_invalid_binding_send_nothing(self):
        session,cancel,c=self.setup_session()
        with self.assertRaisesRegex(RuntimeError,'超出'):drag(session,(400,500),(150,150),cancel)
        c.post_touch_down.assert_not_called()
        session.validate.return_value=False
        with self.assertRaisesRegex(RuntimeError,'停止'):drag(session,(100,500),(150,150),cancel)
        c.post_touch_down.assert_not_called()


class ObservationGuardTests(unittest.TestCase):
    def operations(self):
        from lineup.runner import Operations
        capture=Mock();mouse=Mock(size=(300,250));cancel=Mock();cancel.wait.return_value=False
        vision=Mock();ops=Operations(capture,mouse,vision,cancel,Mock());ops.check=lambda:None
        ops.frame=np.full((250,300,3),120,np.uint8)
        ops.observation=Observation(state='ready',count=0,limit=15,grid=Grid((0,0,250,250),5,5),inventory_rect=(0,150,300,100))
        return ops
    def test_changed_inventory_rejects_stale_coordinates(self):
        ops=self.operations();fresh=ops.frame.copy();fresh[150:]+=30;ops.fresh_frame=lambda:fresh
        with self.assertRaisesRegex(RuntimeError,'库存界面已变化'):ops.guard()
        ops.mouse.click.assert_not_called();ops.vision.observe.assert_not_called()
    def test_changed_limit_rejects_input(self):
        ops=self.operations();ops.fresh_frame=lambda:ops.frame.copy()
        ops.vision.observe.return_value=Observation(state='ready',count=0,limit=5,grid=Grid((0,0,250,250),5,5))
        with self.assertRaisesRegex(RuntimeError,'上阵状态已变化'):ops.guard()
        ops.mouse.click.assert_not_called()
    def test_checker_jitter_uses_verified_grid_when_controls_stay_put(self):
        ops=self.operations();old=Observation(state='ready',count=0,limit=15,grid=Grid((20,20,200,200),5,5),clear=(270,140),inventory_rect=(0,150,300,100))
        ops.observation=old;ops.stabilize_grid(old);fresh=Observation(state='ready',count=0,limit=15,grid=Grid((23,26,203,203),5,5),clear=(270,140),inventory_rect=old.inventory_rect)
        ops.fresh_frame=lambda:ops.frame.copy();ops.vision.observe.return_value=fresh
        self.assertEqual(ops.guard().grid.rect,old.grid.rect)
        ops.mouse.click.assert_not_called()
    def test_control_movement_prevents_reusing_grid_anchor(self):
        ops=self.operations();old=Observation(state='ready',count=0,limit=15,grid=Grid((20,20,200,200),5,5),clear=(270,140))
        ops.stabilize_grid(old);changed=Observation(state='ready',count=0,limit=15,grid=Grid((20,20,200,200),5,5),clear=(270,155))
        with self.assertRaisesRegex(RuntimeError,'位置已变化'):ops.stabilize_grid(changed)
        ops.mouse.click.assert_not_called()
    def test_temporary_unknown_is_reobserved_before_confirmation(self):
        ops=self.operations();ready=Observation(state='ready',count=1,limit=15,grid=Grid((0,0,250,250),5,5))
        ops.snapshot=Mock(side_effect=[RuntimeError('上阵界面尚未识别'),ready,ready])
        self.assertEqual(ops.wait_count(1).count,1);self.assertEqual(ops.snapshot.call_count,3)
        ops.mouse.click.assert_not_called()
    def test_count_alone_without_tile_change_does_not_confirm_drag(self):
        import itertools
        ops=self.operations();ops.pending=(0,ops.frame[6:44,6:44].copy())
        ops.snapshot=Mock(return_value=Observation(state='ready',count=1,limit=15,grid=Grid((0,0,250,250),5,5)))
        with patch('lineup.runner.time.monotonic',side_effect=itertools.count()):
            with self.assertRaisesRegex(RuntimeError,'未确认上阵数量更新'):ops.wait_count(1)
        ops.mouse.click.assert_not_called();self.assertIsNotNone(ops.pending)
    def test_stale_capture_times_out_without_input(self):
        import itertools
        ops=self.operations();ops.capture.read.return_value=(ops.frame,0,1,(300,250))
        with patch('lineup.runner.time.monotonic',side_effect=itertools.count(10)):
            with self.assertRaisesRegex(RuntimeError,'新画面'):ops.fresh_frame()
        ops.mouse.click.assert_not_called()
    def test_paging_swipe_uses_verified_portrait_row_without_long_hold(self):
        ops=self.operations();obs=ops.observation;obs.scroll_line=154
        obs.cards=[{'bounds':(10,160,60,70)},{'bounds':(100,160,60,70)},{'bounds':(200,160,60,70)}]
        ops.guard=Mock(return_value=obs);ops.snapshot=Mock(return_value=obs)
        with patch('lineup.runner.drag') as swipe:
            ops.scroll(1)
        args=swipe.call_args.args
        self.assertGreater(args[1][1],160);self.assertLess(args[1][1],230)
        self.assertEqual(args[1][1],args[2][1]);self.assertGreater(args[1][0],args[2][0])
        self.assertEqual(swipe.call_args.kwargs['hold'],0)
    def test_unverified_card_row_does_not_swipe(self):
        ops=self.operations();ops.guard=Mock(return_value=ops.observation)
        with patch('lineup.runner.drag') as swipe:
            with self.assertRaisesRegex(RuntimeError,'滑动区域'):ops.scroll(1)
        swipe.assert_not_called()
    def test_accidental_deployment_during_paging_stops_search(self):
        ops=self.operations();obs=ops.observation
        obs.cards=[{'bounds':(10,160,60,70)},{'bounds':(200,160,60,70)}]
        ops.guard=Mock(return_value=obs);ops.snapshot=Mock(return_value=Observation(count=1,limit=15))
        with patch('lineup.runner.drag'):
            with self.assertRaisesRegex(RuntimeError,'数量发生变化'):ops.scroll(1)
    def test_find_checks_current_page_before_scrolling_back(self):
        ops=self.operations();card={'id':'dozy','point':(60,180)};ops.page=Mock(return_value=[card]);ops.rewind=Mock();ops.select_element=Mock(return_value=False)
        self.assertIs(ops.find_available('dozy'),card);ops.rewind.assert_not_called()


class PortraitCacheTests(unittest.TestCase):
    def test_only_confirmed_units_enter_session_cache(self):
        from lineup.recognition import PortraitCache
        cache=PortraitCache();image=read_image(ASSETS/'lineup/tatari/serrabloom.png')[:,:,:3]
        cache.add('?',image);self.assertIsNone(cache.match(image))
        cache.add('serrabloom',image);self.assertEqual(cache.match(image)['id'],'serrabloom')
    def test_other_characters_and_ambiguous_templates_are_rejected(self):
        from lineup.recognition import PortraitCache
        cache=PortraitCache();a=read_image(ASSETS/'lineup/tatari/serrabloom.png')[:,:,:3];b=read_image(ASSETS/'lineup/tatari/dozy.png')[:,:,:3]
        cache.add('serrabloom',a);self.assertIsNone(cache.match(b))
        cache.add('duplicate',a);self.assertIsNone(cache.match(a))


class ElementInventoryTests(unittest.TestCase):
    operations=ObservationGuardTests.operations
    def test_live_rows_share_columns_despite_inner_border_and_missing_last_card(self):
        frame=read_image(FIXTURES/'live-empty-inventory.png');obs=Vision().observe(frame)
        self.assertEqual(len(obs.cards),10)
        first,second=obs.cards[:5],obs.cards[5:]
        self.assertEqual([c['bounds'][0] for c in first],[c['bounds'][0] for c in second])
        ops=self.operations();ops.frame=frame;ops.snapshot=Mock(return_value=obs)
        cards=ops.page(allowed_ids={'synthhog'})
        self.assertEqual([i for i,c in enumerate(cards) if c['id']=='synthhog'],[9])
        self.assertLess(cards[9]['point'][1],obs.filters['lightning'][1])
    def test_one_shaded_badge_does_not_reset_verified_lightning_page(self):
        ops=self.operations();obs=ops.observation
        obs.filters={'lightning':(200,240),'all':(30,240)}
        obs.cards=[{'element':'rock'}]+[{'element':'lightning'} for _ in range(8)]
        ops.snapshot=Mock(return_value=obs);ops.guard=Mock(return_value=obs)
        self.assertTrue(ops.select_element('lightning'))
        self.assertTrue(ops.select_element('lightning'))
        ops.mouse.click.assert_called_once_with((200,240))
    def test_visible_filter_row_and_missing_card_border_are_recovered(self):
        image=read_image(FIXTURES/'formation-fifteen.png');obs=Vision().observe(image)
        self.assertEqual(set(obs.filters),{'all','water','fire','grass','rock','lightning'})
        self.assertEqual(len(obs.cards),10)
        self.assertEqual([c['element'] for c in obs.cards],['grass','water','fire','lightning','grass','fire','water','lightning','lightning','lightning'])
        self.assertTrue(obs.inventory_rect[1]<=obs.scroll_line<min(c['bounds'][1] for c in obs.cards))
    def test_visible_inventory_portraits_match_all_ten_actual_identities(self):
        ops=self.operations();ops.frame=read_image(FIXTURES/'formation-fifteen.png')
        obs=Vision().observe(ops.frame);ops.snapshot=Mock(return_value=obs)
        cards=ops.page()
        self.assertEqual([c['id'] for c in cards],['manteeny','ripplewing','firecoil','zappur','trippet','sizribb','droppit','cheerlet','voltfawn','synthhog'])
    def test_filtered_match_does_not_use_other_element_templates(self):
        from lineup.recognition import identify
        image=read_image(ASSETS/'lineup/tatari/serrabloom.png')
        result=identify(image,allowed_ids={'serrabloom'})
        self.assertEqual(result['id'],'serrabloom');self.assertEqual([r['id'] for r in result['candidates']],['serrabloom'])
    def test_filter_icons_can_move_and_inventory_badges_are_not_filter_buttons(self):
        vision=Vision();image=read_image(FIXTURES/'formation-fifteen.png')
        scaled=cv2.resize(image,(540,997));strip=scaled[839:900].copy();shifted=scaled.copy()
        shifted[839:900]=0;shifted[820:881]=strip
        filters=vision.find_filters(shifted,735,922)
        self.assertEqual(len(filters),6);self.assertLess(filters['water'][1],860)
        self.assertEqual(vision.find_filters(scaled,630,830),{})
    def test_collapsed_filter_layout_keeps_verified_swipe_margin(self):
        obs=Vision().observe(read_image(FIXTURES/'formation-five.png'))
        self.assertEqual(obs.filters,{});self.assertGreaterEqual(len(obs.cards),8)
        self.assertIsNotNone(obs.scroll_line)
    def test_selected_element_requires_matching_inventory_badges(self):
        ops=self.operations();obs=ops.observation;obs.filters={'grass':(200,240)};obs.cards=[{'element':'water'}]
        ops.snapshot=Mock(return_value=obs);ops.guard=Mock(return_value=obs)
        with self.assertRaisesRegex(RuntimeError,'筛选生效'):ops.select_element('grass')
        self.assertIsNone(ops.element);ops.mouse.click.assert_called_once_with((200,240))
    def test_ambiguous_badges_reset_to_all_instead_of_aborting(self):
        ops=self.operations();obs=ops.observation;obs.filters={'grass':(200,240),'all':(30,240)};obs.cards=[{'element':'water'}]
        ops.snapshot=Mock(return_value=obs);ops.guard=Mock(return_value=obs)
        self.assertFalse(ops.select_element('grass'))
        self.assertEqual(ops.mouse.click.call_args_list,[unittest.mock.call((200,240)),unittest.mock.call((30,240))])
        self.assertIsNone(ops.element)
    def test_visible_same_family_is_deployed_without_hunting_another_stage(self):
        ops=self.operations();ops.select_element=Mock();ops.rewind=Mock();ops.scroll=Mock()
        ops.observation.cards=[{}]
        ops.page=Mock(side_effect=[[{'id':'serrabloom'}],[{'id':'serrabloom'}],[{'id':'manteeny'}]])
        self.assertEqual(ops.find_available('manteeny')['id'],'serrabloom')
        ops.scroll.assert_not_called();ops.rewind.assert_not_called()
    def test_later_page_candidate_uses_its_current_coordinates(self):
        ops=self.operations();ops.select_element=Mock();ops.rewind=Mock();ops.scroll=Mock();ops.observation.cards=[{}]
        old={'id':'serrabloom','point':(50,180)};new={'id':'serrabloom','point':(150,180)}
        def turn(direction):ops.frame[:]=ops.frame[0,0,0]+20;return True
        ops.scroll=Mock(side_effect=turn);ops.page=Mock(side_effect=[[],[new]])
        self.assertIs(ops.find_available('manteeny'),new);ops.rewind.assert_not_called()
        ops.scroll.assert_called_once_with(1)
    def test_other_stage_of_already_deployed_family_is_not_searched(self):
        ops=self.operations();ops.select_element=Mock();ops.page=Mock()
        self.assertIsNone(ops.find_available('manteeny',{'serrabloom'}))
        ops.select_element.assert_not_called();ops.page.assert_not_called()
    def test_retained_inventory_identity_is_not_deployed_twice(self):
        ops=self.operations();ops.select_element=Mock();ops.page=Mock();ops.rewind=Mock()
        used={r['id'] for r in load_catalog() if r['family']=='manteeny'}
        self.assertIsNone(ops.find_available('manteeny',used));ops.page.assert_not_called()
    def test_visible_card_without_level_is_still_a_deployable_candidate(self):
        ops=self.operations();image=read_image(FIXTURES/'live-rock-inventory.png');vision=Vision();obs=vision.observe(image)
        ops.frame=image;ops.snapshot=Mock(return_value=obs);ops.select_element=Mock();ops.rewind=Mock()
        card=ops.find_available('rubblet')
        self.assertEqual(card['id'],'rubblet');ops.rewind.assert_not_called()
        x,y,width,height=map(round,card['bounds'])
        words=vision.text(image[y:y+round(height*.35),x:x+width,:3])
        self.assertFalse(any('lv' in text.lower() for _,text,_ in words))
    def test_filter_confirmed_on_two_fresh_frames_and_reused(self):
        ops=self.operations();obs=ops.observation;obs.filters={'grass':(200,240)};obs.cards=[{'element':'grass'}]
        ops.snapshot=Mock(return_value=obs);ops.guard=Mock(return_value=obs)
        self.assertTrue(ops.select_element('grass'));self.assertTrue(ops.select_element('grass'))
        ops.mouse.click.assert_called_once();self.assertEqual(ops.element,'grass')
    def test_moving_filter_button_rejects_old_click_position(self):
        ops=self.operations();obs=ops.observation;obs.filters={'grass':(200,240)}
        ops.snapshot=Mock(return_value=obs);ops.guard=Mock(return_value=Observation(filters={'grass':(220,240)}))
        with self.assertRaisesRegex(RuntimeError,'按钮位置已变化'):ops.select_element('grass')
        ops.mouse.click.assert_not_called()
    def test_find_filters_before_reacquiring_card_position(self):
        ops=self.operations();ops.targets=['manteeny'];ops.select_element=Mock(return_value=True)
        card={'id':'serrabloom','point':(60,180)};ops.page=Mock(return_value=[card]);ops.rewind=Mock();ops.select_element=Mock(return_value=False)
        self.assertIs(ops.find_available('serrabloom'),card);ops.select_element.assert_called_once_with('grass')
        ops.rewind.assert_not_called()


class DeployedBoardTests(unittest.TestCase):
    operations=ObservationGuardTests.operations
    def test_large_new_lineup_does_not_expand_grid_and_all_fifteen_are_identified(self):
        image=read_image(FIXTURES/'live-new-dense-board.png');v=Vision();obs=v.observe(image)
        old=Vision().observe(read_image(FIXTURES/'live-empty-inventory.png'))
        self.assertLess(max(abs(a-b) for a,b in zip(obs.grid.rect,old.grid.rect)),8)
        units=v.board(image,obs)
        self.assertEqual({u['index']:u['id'] for u in units},{1:'sizribb',2:'ospisces',3:'pyropup',4:'blowfin',6:'firecoil',7:'manteeny',8:'cheerlet',9:'sunfleur',10:'blueflick',11:'ripplewing',12:'pyroprawn',13:'trippet',17:'firefox',18:'synthhog',22:'blubbles'})
    def test_new_reference_identifies_dolphin_t3_without_lowering_confidence(self):
        result=import_formation(read_image(FIXTURES/'formation-dolphin-t3.png'))
        self.assertEqual(result['cells'][22],'aquariel')
        self.assertGreaterEqual(result['details'][22]['score'],.82)
        self.assertEqual(sum(k is not None for k in result['cells']),15)
    def test_small_portrait_formation_preserves_all_positions_after_jpeg_compression(self):
        image=read_image(FIXTURES/'formation-small-sprites.png')
        expected=[None,'hellhound','serrabloom',None,None,None,'cheerspring','armorjaw','blitzmane',None,
                  'magmusk','waveflutter','pyroclobster','charflutter','embertail',None,'hyphoria','azurion',
                  'sonarbat','solaflora',None,None,'flarevix',None,None]
        compressed=cv2.imdecode(cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,85])[1],cv2.IMREAD_COLOR)
        for frame in (image,compressed):
            with self.subTest(compressed=frame is compressed):
                result=import_formation(frame)
                self.assertEqual(result['cells'],expected)
                self.assertGreaterEqual(result['details'][2]['score'],.82)
    def test_small_portrait_role_badge_and_wrong_cell_center_remain_uncertain(self):
        from lineup.recognition import identify
        image=read_image(FIXTURES/'formation-small-sprites.png');grid=grayscale_grid(image)
        x,y,right,bottom=grid.tile(2,0)
        self.assertEqual(identify(image[y:y+24,right-25:right,:3])['id'],'?')
        self.assertEqual(identify(image[y:bottom,x:right,:3],center_region=(0,0,10,10))['id'],'?')
    def test_move_confirms_identity_when_neighbor_effects_remain_in_source(self):
        ops=self.operations();old=ops.frame.copy()
        cv2.rectangle(old,(10,10),(30,30),(0,0,0),3)
        ops.moving=[(0,old[6:44,6:44].copy()),(1,old[6:44,56:94].copy())]
        cv2.rectangle(ops.frame,(18,10),(38,30),(0,0,0),3)
        cv2.rectangle(ops.frame,(60,10),(80,30),(0,0,0),3)
        ops.moving_identity='dozy';ops.observation.count=1;ops.snapshot=Mock(return_value=ops.observation)
        ops.vision.unit.side_effect=lambda f,o,i,expected=None:{'id':'?' if i==0 else 'dozy'}
        self.assertEqual(ops.wait_move(1).count,1)
        self.assertEqual(ops.board_identities,{1:'dozy'})
    def test_source_identity_still_present_rejects_false_move_confirmation(self):
        import itertools
        ops=self.operations();old=ops.frame.copy()
        ops.moving=[(0,old[6:44,6:44].copy()),(1,old[6:44,56:94].copy())]
        cv2.rectangle(ops.frame,(18,10),(38,30),(0,0,0),3)
        cv2.rectangle(ops.frame,(60,10),(80,30),(0,0,0),3)
        ops.moving_identity='dozy';ops.observation.count=1;ops.snapshot=Mock(return_value=ops.observation)
        ops.vision.unit.return_value={'id':'dozy'}
        with patch('lineup.runner.time.monotonic',side_effect=itertools.count()):
            with self.assertRaisesRegex(RuntimeError,'移动完成'):ops.wait_move(1)
    def test_empty_board_ignores_enemy_portraits_above_player_grid(self):
        image=read_image(FIXTURES/'formation-five.png');vision=Vision();obs=vision.observe(image)
        self.assertEqual(vision.board(image,obs),[])
    def test_sprite_cells_are_recognized_inside_grayscale_player_grid(self):
        image=read_image(FIXTURES/'formation-fifteen.png');vision=Vision();obs=vision.observe(image)
        for index,identity in [(6,'dozy'),(8,'serrabloom')]:
            sprite=read_image(ASSETS/f'lineup/tatari/{identity}.png')
            ax,ay,aw,ah=cv2.boundingRect((sprite[:,:,3]>128).astype(np.uint8));sprite=sprite[ay:ay+ah,ax:ax+aw]
            sprite=cv2.resize(sprite,(48,48));cx,cy=map(round,obs.grid.center(index));x,y=cx-24,cy-24
            alpha=sprite[:,:,3:4]/255
            image[y:y+48,x:x+48,:3]=(sprite[:,:,:3]*alpha+image[y:y+48,x:x+48,:3]*(1-alpha)).astype(np.uint8)
        obs.count=2
        units=vision.board(image,obs)
        self.assertEqual({u['index']:u['id'] for u in units},{6:'dozy',8:'serrabloom'})
    def test_changed_source_prevents_withdraw(self):
        ops=self.operations();ops.board_reference=ops.frame.copy();ops.frame[:50,:50]=220
        ops.guard=Mock(return_value=ops.observation)
        with self.assertRaisesRegex(RuntimeError,'位置已变化'):ops.withdraw(0,0)
        ops.mouse.click.assert_not_called()
    def test_same_count_without_movement_does_not_confirm(self):
        import itertools
        ops=self.operations();ops.moving=[(0,ops.frame[6:44,6:44].copy()),(1,ops.frame[6:44,56:94].copy())]
        ops.snapshot=Mock(return_value=ops.observation)
        with patch('lineup.runner.time.monotonic',side_effect=itertools.count()):
            with self.assertRaisesRegex(RuntimeError,'移动完成'):ops.wait_move(0)
    def test_card_changed_after_intermediate_snapshot_prevents_drag(self):
        ops=self.operations();obs=ops.observation;ops.board_guard=Mock(return_value=obs)
        card={'id':'dozy','point':(40,180),'bounds':(10,160,50,60),'patch':np.zeros((60,50,3),np.uint8)}
        with patch('lineup.runner.drag') as action:
            with self.assertRaisesRegex(RuntimeError,'库存塔塔位置'):ops.deploy(card,obs.grid.center(0),0,0)
        action.assert_not_called()
    def test_animation_with_source_still_occupied_does_not_confirm_move(self):
        import itertools
        ops=self.operations();old=ops.frame.copy()
        cv2.rectangle(old,(10,10),(30,30),(0,0,0),3)
        ops.moving=[(0,old[6:44,6:44].copy()),(1,old[6:44,56:94].copy())]
        cv2.rectangle(ops.frame,(14,14),(34,34),(0,0,0),3)
        cv2.rectangle(ops.frame,(60,10),(80,30),(0,0,0),3)
        ops.observation.count=1;ops.snapshot=Mock(return_value=ops.observation)
        with patch('lineup.runner.time.monotonic',side_effect=itertools.count()):
            with self.assertRaisesRegex(RuntimeError,'移动完成'):ops.wait_move(1)
    def test_changed_count_with_target_still_empty_does_not_confirm_deploy(self):
        import itertools
        ops=self.operations();ops.pending=(0,ops.frame[6:44,6:44].copy());ops.pending_kind='deploy'
        ops.frame[:50,:50]=150;ops.observation.count=1;ops.snapshot=Mock(return_value=ops.observation)
        with patch('lineup.runner.time.monotonic',side_effect=itertools.count()):
            with self.assertRaisesRegex(RuntimeError,'数量更新'):ops.wait_count(1)
    def test_real_deployed_sprites_include_large_cheerlet_without_neighbor_leak(self):
        image=read_image(FIXTURES/'live-deployed.png');vision=Vision();obs=vision.observe(image)
        units=vision.board(image,obs)
        self.assertEqual({u['index']:u['id'] for u in units},{6:'firecoil',8:'cheerlet',10:'manteeny',11:'ripplewing',14:'rockfu',22:'droppit'})
        self.assertEqual(vision.unit(image,obs,7)['id'],'?')
    def test_latest_user_formation_preserves_all_fifteen_positions(self):
        formation=import_formation(read_image(FIXTURES/'formation-user-15.png'))
        actual={i:k for i,k in enumerate(formation['cells']) if k is not None}
        self.assertEqual(actual,{1:'rockong',2:'rockshell',3:'rockzilla',4:'snoozebo',6:'charflutter',7:'clangnaga',8:'cheerspring',9:'sonarbat',10:'serrabloom',11:'waveflutter',12:'zenscarab',13:'hyphoria',14:'zorrock',17:'rockhog',22:'tideon'})
    def test_idle_animation_is_allowed_when_source_identity_and_occupancy_hold(self):
        ops=self.operations();image=read_image(FIXTURES/'live-deployed.png');vision=Vision();obs=vision.observe(image)
        ops.frame=image.copy();ops.observation=obs;ops.board_reference=image.copy();ops.board_identities={14:'rockfu'}
        x,y,right,bottom=obs.grid.tile(14,0)
        ops.frame[y:bottom,x:right]=np.clip(ops.frame[y:bottom,x:right].astype(int)+24,0,255).astype(np.uint8)
        ops.guard=Mock(return_value=obs);ops.vision.unit.return_value={'id':'rockfu'}
        self.assertIs(ops.board_guard([14,1],6),obs)
    def test_replaced_source_identity_prevents_move_despite_same_count(self):
        ops=self.operations();image=read_image(FIXTURES/'live-deployed.png');vision=Vision();obs=vision.observe(image)
        ops.frame=image;ops.observation=obs;ops.board_reference=image.copy();ops.board_identities={14:'rockfu'}
        ops.guard=Mock(return_value=obs);ops.vision.unit.return_value={'id':'punchimp'}
        with patch('lineup.runner.drag') as action:
            with self.assertRaisesRegex(RuntimeError,'身份已变化'):ops.move(14,1,6)
        action.assert_not_called()


if __name__=='__main__':unittest.main()
