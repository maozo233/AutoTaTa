"""Grouped immediate deployment, independent 3×4 geometry and safe reuse."""
import threading,unittest
from unittest.mock import Mock,patch
import cv2,numpy as np
from tests import test_lineup as helpers
from lineup.catalog import load_catalog,choose_available
from lineup.engine import execute
from lineup.runner import Operations
from lineup.vision import Vision,Grid,Observation,import_formation,narrow_reference_grid,read_image

FIXTURES=helpers.FIXTURES


class BatchFake(helpers.FakeOperations):
    def __init__(self,*args,columns=5,**kwargs):
        super().__init__(*args,**kwargs);self.columns=columns;self.requests=[]
    def snapshot(self):
        return Observation(state='ready',count=self.count,limit=self.limit,
            grid=Grid((0,0,250,200 if self.columns==3 else 250),self.columns,4 if self.columns==3 else 5))
    def find_next(self,requests,used):
        self.requests.append(dict(requests))
        # Inventory order intentionally differs from requested slot order.
        for card in self.inventory:
            for index,wanted in requests.items():
                if choose_available(wanted,[card],used):return index,card
        return None


class BatchDeploymentTests(unittest.TestCase):
    def test_same_element_stays_together_and_visible_later_target_deploys_first(self):
        ops=BatchFake(inventory=[{'id':'cobbledon'},{'id':'serrabloom'},{'id':'snoozebo'}])
        plan=execute(ops,['dozy','manteeny','rubblet']+[None]*22,5,lambda e:None)
        self.assertEqual(ops.calls,[('drag','cobbledon',2),('drag','snoozebo',0),('drag','serrabloom',1)])
        self.assertEqual(ops.requests,[{0:'dozy',2:'rubblet'},{0:'dozy'},{1:'manteeny'}])
        self.assertEqual(len(plan['placements']),3)
    def test_one_missing_group_does_not_prevent_other_elements(self):
        ops=BatchFake(inventory=[{'id':'serrabloom'}])
        plan=execute(ops,['dozy','rubblet','manteeny']+[None]*22,5,lambda e:None)
        self.assertEqual([i['index'] for i in plan['issues']],[0,1])
        self.assertEqual(ops.units,{2:'serrabloom'})
    def test_full_three_by_four_withdraws_before_replacement_and_never_exceeds_five(self):
        ops=BatchFake({0:'rubblet',3:'rockfu',5:'rizzler',8:'taptail',10:'watchroo'},
            [{'id':'snoozebo'}],columns=3,limit=5)
        cells=['cobbledon',None,'dozy','rockfu',None,'rizzler',None,None,'taptail',None,None,None]
        plan=execute(ops,cells,3,lambda e:None)
        self.assertEqual(ops.calls,[('withdraw',10),('drag','snoozebo',2)])
        self.assertEqual(ops.count,5);self.assertEqual(len(plan['placements']),5)
    def test_three_by_four_reports_sixth_target_without_sending_extra_drag(self):
        names=['dozy','rubblet','rockfu','rizzler','taptail','watchroo']
        ops=BatchFake(inventory=[{'id':k} for k in names],columns=3,limit=5)
        plan=execute(ops,names+[None]*6,3,lambda e:None)
        self.assertEqual(ops.count,5);self.assertEqual(len(ops.calls),5)
        self.assertEqual(plan['issues'],[{'index':5,'reason':'超过上阵上限'}])
    def test_wrong_element_is_marked_instead_of_switching_inventory(self):
        ops=BatchFake(inventory=[{'id':'rubblet'},{'id':'serrabloom'}],columns=3,limit=5)
        plan=execute(ops,['rubblet','manteeny']+[None]*10,3,lambda e:None)
        self.assertEqual(ops.units,{0:'rubblet'});self.assertEqual(ops.requests,[{0:'rubblet'}])
        self.assertIn('当前活动属性',plan['issues'][0]['reason'])
    def test_batch_result_for_wrong_family_is_rejected_before_input(self):
        ops=BatchFake();ops.find_next=Mock(return_value=(0,{'id':'rockwu'}))
        with self.assertRaisesRegex(RuntimeError,'不一致'):execute(ops,['dozy']+[None]*24,5,lambda e:None)
        self.assertEqual(ops.calls,[])


class ReuseTests(unittest.TestCase):
    operations=helpers.ObservationGuardTests.operations
    def test_three_by_four_never_taps_even_a_visible_filter(self):
        ops=self.operations();o=ops.observation;o.grid=Grid((20,20,150,200),3,4);o.limit=5
        o.filters={'rock':(200,240)};ops.snapshot=Mock(return_value=o)
        self.assertFalse(ops.select_element('rock'));ops.mouse.click.assert_not_called()
    def test_pending_families_share_one_page_search_and_stop_at_visible_match(self):
        ops=self.operations();ops.select_element=Mock();ops.scroll=Mock()
        ops.page=Mock(return_value=[{'id':'cobbledon','point':(80,180)}])
        index,card=ops.find_next({0:'dozy',2:'rubblet'})
        self.assertEqual((index,card['id']),(2,'cobbledon'));ops.scroll.assert_not_called()
        allowed=ops.page.call_args.kwargs['allowed_ids']
        self.assertIn('snoozebo',allowed);self.assertIn('cobbledon',allowed);self.assertNotIn('serrabloom',allowed)
    def test_reused_action_state_still_rejects_changed_inventory_before_drag(self):
        ops=self.operations();obs=ops.action_state();ops.fresh_frame=Mock(return_value=np.zeros_like(ops.frame))
        self.assertIs(obs,ops.observation)
        with self.assertRaisesRegex(RuntimeError,'库存界面已变化'):
            ops.deploy({'id':'dozy','patch':np.zeros((2,2,3),np.uint8)},(25,25),0,0)
        ops.mouse.click.assert_not_called()
    def test_reused_unit_results_are_keyed_by_pixels_and_requested_identity(self):
        v=Vision();im=read_image(FIXTURES/'three-four-live.png');obs=v.observe(im)
        with patch('lineup.vision.identify',wraps=__import__('lineup.recognition',fromlist=['identify']).identify) as identify:
            self.assertEqual(v.unit(im,obs,0)['id'],'rubblet');n=identify.call_count
            self.assertEqual(v.unit(im,obs,0)['id'],'rubblet');self.assertEqual(identify.call_count,n)
            self.assertEqual(v.unit(im,obs,0,'rubblet')['id'],'rubblet');self.assertGreater(identify.call_count,n)
            n=identify.call_count;changed=im.copy();x,y=map(round,obs.grid.center(0));changed[y,x]=255
            v.unit(changed,obs,0);self.assertGreater(identify.call_count,n)
    def test_weak_preferred_board_match_falls_back_to_catalog(self):
        v=Vision();im=np.zeros((200,200,3),np.uint8);obs=Observation(count=1,grid=Grid((0,0,200,200),1,1))
        with patch('lineup.vision.occupied_cell',return_value=True),patch.object(v,'unit',side_effect=[{'id':'dozy','score':.85},{'id':'rubblet','score':.96}]):
            self.assertEqual(v.board(im,obs,preferred_ids={'dozy'})[0]['id'],'rubblet')
    def test_filter_cache_reuses_only_identical_region(self):
        v=Vision();im=read_image(FIXTURES/'formation-fifteen.png');im=cv2.resize(im,(540,997))
        with patch('lineup.vision.cv2.matchTemplate',wraps=cv2.matchTemplate) as match:
            first=v.find_filters(im,735,922);n=match.call_count
            self.assertTrue(first);self.assertEqual(v.find_filters(im,735,922),first);self.assertEqual(match.call_count,n)
            changed=im.copy();changed[840:900]=0;v.find_filters(changed,735,922);self.assertGreater(match.call_count,n)


class ThreeFourScreenshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cv2.setNumThreads(1)
    def test_live_player_grid_has_twelve_cells_and_excludes_enemies(self):
        im=read_image(FIXTURES/'three-four-live.png');v=Vision();o=v.observe(im)
        self.assertEqual((o.count,o.limit,o.grid.columns,o.grid.rows),(5,5,3,4))
        self.assertGreater(o.grid.rect[1],320);self.assertLess(o.grid.rect[1]+o.grid.rect[3],565)
        self.assertEqual([(u['index'],u['id']) for u in v.board(im,o)],[(0,'rubblet'),(3,'rockfu'),(5,'rizzler'),(8,'taptail'),(10,'watchroo')])
    def test_user_live_board_reconciles_to_reference_with_moves_and_two_replacements(self):
        im=read_image(FIXTURES/'three-four-live.png');v=Vision();obs=v.observe(im)
        units={u['index']:u['id'] for u in v.board(im,obs)}
        formation=import_formation(read_image(FIXTURES/'three-four-reference.png'),3)
        ops=BatchFake(units,[{'id':'cragolin'},{'id':'humbleetle'}],columns=3,limit=5)
        plan=execute(ops,formation['cells'],3,lambda e:None)
        self.assertEqual(ops.units,{0:'cragolin',2:'rubblet',4:'rizzler',7:'humbleetle',10:'taptail'})
        self.assertEqual(sum(c[0]=='move' for c in ops.calls),3)
        self.assertEqual(sum(c[0]=='withdraw' for c in ops.calls),2)
        self.assertEqual(sum(c[0]=='drag' for c in ops.calls),2)
        self.assertEqual(len(plan['placements']),5);self.assertEqual(plan['issues'],[])
    def test_three_user_reference_styles_preserve_positions_and_only_five_units(self):
        cases={
          'three-four-full-reference.png':{1:'cobbledon',2:'snoozebo',4:'rockshell',6:'rockhog',9:'humbleetle'},
          'three-four-reference.png':{0:'cragolin',2:'cobbledon',4:'rizzler',7:'humbleetle',10:'clangnaga'},
          'three-four-cropped-reference.png':{0:'snoozebo',1:'cobbledon',2:'turtuff',8:'humbleetle',9:'clangnaga'}}
        for name,units in cases.items():
            with self.subTest(name=name):
                result=import_formation(read_image(FIXTURES/name),3)
                self.assertEqual((result['grid'].columns,result['grid'].rows),(3,4))
                self.assertEqual(result['cells'],[units.get(i) for i in range(12)])
    def test_narrow_grid_uses_grayscale_and_rejects_uniform_background(self):
        im=read_image(FIXTURES/'three-four-cropped-reference.png')
        gray=cv2.cvtColor(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
        self.assertEqual(narrow_reference_grid(im).rect,narrow_reference_grid(gray).rect)
        self.assertIsNone(narrow_reference_grid(np.full_like(im,160)))
    def test_full_and_cropped_references_keep_positions_after_jpeg_and_scaling(self):
        for name,expected in (
            ('three-four-full-reference.png',{1:'cobbledon',2:'snoozebo',4:'rockshell',6:'rockhog',9:'humbleetle'}),
            ('three-four-cropped-reference.png',{0:'snoozebo',1:'cobbledon',2:'turtuff',8:'humbleetle',9:'clangnaga'})):
            im=read_image(FIXTURES/name)
            jpeg=cv2.imdecode(cv2.imencode('.jpg',im,[cv2.IMWRITE_JPEG_QUALITY,85])[1],cv2.IMREAD_COLOR)
            for kind,frame in [('scaled',cv2.resize(im,None,fx=1.4,fy=1.4)),('jpeg',jpeg)]:
                with self.subTest(name=name,kind=kind):
                    self.assertEqual(import_formation(frame,3)['cells'],[expected.get(i) for i in range(12)])


if __name__=='__main__':unittest.main()
