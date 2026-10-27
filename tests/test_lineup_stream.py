"""Progressive image import and deployment share cancellation, never inputs."""
import os,subprocess,sys,threading,unittest
from pathlib import Path
from unittest.mock import Mock
import cv2,numpy as np
from lineup.engine import FormationStream,execute_stream
from lineup.vision import import_formation,checker_reference_grid,read_image
from tests.test_lineup_batch import BatchFake

ROOT=Path(__file__).resolve().parents[1]
EXPECTED=['cobbledon','clawzor',None,'stalkerix',None,None,'cheerlet','blitzmane','firecoil','pyrohound',
          'zapooch','frostique','sparkdoe',None,'pyroprawn',None,None,None,None,'frugagon',
          'rattlecoil',None,None,'cluckeroo','azurion']


class ShiftedReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cv2.setNumThreads(1)
    def test_original_and_jpeg_preserve_fifteen_units_and_river_empty_cells(self):
        image=read_image(ROOT/'tests/fixtures/lineup/formation-shifted-checker.png')
        jpeg=cv2.imdecode(cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,85])[1],cv2.IMREAD_COLOR)
        for label,frame in [('original',image),('jpeg',jpeg)]:
            with self.subTest(label=label):
                published=[]
                result=import_formation(frame,cell_ready=lambda i,r,g:published.append((i,r['id'])))
                self.assertEqual(result['cells'],EXPECTED)
                self.assertEqual(published,list(enumerate(EXPECTED)))
                self.assertLess(result['grid'].rect[1],40)
    def test_grid_uses_grayscale_after_scaling_and_rejects_flat_or_gradient_images(self):
        im=read_image(ROOT/'tests/fixtures/lineup/formation-shifted-checker.png')
        im=cv2.resize(im,None,fx=1.4,fy=1.4)
        gray=cv2.cvtColor(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
        grid=checker_reference_grid(im)
        self.assertEqual(grid,checker_reference_grid(gray))
        self.assertLess(grid.rect[1],60)
        self.assertLess(grid.rect[3],grid.rect[2])
        for frame in (np.full_like(im,200),np.repeat(np.tile(np.linspace(80,220,im.shape[1],dtype=np.uint8),(im.shape[0],1))[:,:,None],3,axis=2)):
            self.assertIsNone(checker_reference_grid(frame))


class StreamingDeploymentTests(unittest.TestCase):
    def run_thread(self,ops,stream,columns=5):
        cancelled=threading.Event();results=[];errors=[]
        def work():
            try:results.append(execute_stream(ops,stream,columns,lambda e:None,cancelled))
            except Exception as exc:errors.append(exc)
        thread=threading.Thread(target=work,daemon=True);thread.start()
        self.addCleanup(lambda:(cancelled.set(),thread.join(2)))
        return thread,cancelled,results,errors
    def test_first_confirmed_unit_deploys_before_image_finishes_without_second_board_scan(self):
        stream=FormationStream(25);stream.put(0,{'id':'dozy'})
        ops=BatchFake(inventory=[{'id':'snoozebo'},{'id':'serrabloom'}]);deployed=threading.Event()
        deploy=ops.deploy;ops.board=Mock(wraps=ops.board)
        def send(*args):deploy(*args);deployed.set()
        ops.deploy=send
        thread,cancelled,results,errors=self.run_thread(ops,stream)
        self.assertTrue(deployed.wait(2));self.assertFalse(stream.read()[1])
        stream.finish({'cells':['dozy','manteeny']+[None]*23});thread.join(2)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        self.assertEqual(ops.units,{0:'snoozebo',1:'serrabloom'})
        self.assertEqual(len(results[0]['placements']),2);ops.board.assert_called_once()
    def test_retained_tower_moves_early_but_other_units_are_not_withdrawn_until_complete(self):
        stream=FormationStream(25);stream.put(0,{'id':'dozy'})
        ops=BatchFake({4:'snoozebo',8:'rockwu'},[]);moved=threading.Event();move=ops.move
        def send(*args):move(*args);moved.set()
        ops.move=send
        thread,_,results,errors=self.run_thread(ops,stream)
        self.assertTrue(moved.wait(2));self.assertEqual(ops.calls,[('move',4,0)])
        stream.finish({'cells':['dozy']+[None]*24});thread.join(2)
        self.assertEqual(errors,[]);self.assertEqual(ops.calls,[('move',4,0),('withdraw',8)])
    def test_full_board_waits_for_complete_reference_before_removing_blocker(self):
        stream=FormationStream(25);stream.put(0,{'id':'dozy'});waiting=threading.Event();wait=stream.wait
        def idle(v):waiting.set();wait(v)
        stream.wait=idle;ops=BatchFake({0:'rockwu'},[{'id':'snoozebo'}],limit=1)
        thread,_,_,errors=self.run_thread(ops,stream)
        self.assertTrue(waiting.wait(2));self.assertEqual(ops.calls,[])
        stream.finish({'cells':['dozy']+[None]*24});thread.join(2)
        self.assertEqual(errors,[]);self.assertEqual(ops.calls,[('withdraw',0),('drag','snoozebo',0)])
    def test_stop_while_waiting_releases_without_any_input(self):
        stream=FormationStream(25);waiting=threading.Event();wait=stream.wait
        stream.wait=lambda v:(waiting.set(),wait(v));ops=BatchFake()
        thread,cancelled,_,errors=self.run_thread(ops,stream)
        self.assertTrue(waiting.wait(2));cancelled.set();thread.join(2)
        self.assertFalse(thread.is_alive());self.assertIn('已停止',str(errors[0]));self.assertEqual(ops.calls,[])
    def test_failed_image_cannot_send_a_pending_inventory_drag(self):
        stream=FormationStream(25);stream.put(0,{'id':'dozy'});ops=BatchFake()
        def fail(*args):stream.fail('图片识别失败');return 0,{'id':'dozy'}
        ops.find_next=fail
        thread,_,_,errors=self.run_thread(ops,stream);thread.join(2)
        self.assertFalse(thread.is_alive());self.assertIn('图片识别失败',str(errors[0]));self.assertEqual(ops.calls,[])
    def test_three_four_never_adds_wrong_element_before_reference_finishes(self):
        stream=FormationStream(12);stream.put(0,{'id':'manteeny'});stream.put(1,{'id':'dozy'})
        ops=BatchFake(inventory=[{'id':'snoozebo'},{'id':'serrabloom'}],columns=3,limit=5)
        snapshot=ops.snapshot
        def observe():
            result=snapshot();result.cards=[{'element':'rock'}]*6;return result
        ops.snapshot=observe;deployed=threading.Event();deploy=ops.deploy
        def send(*args):deploy(*args);deployed.set()
        ops.deploy=send
        thread,_,_,errors=self.run_thread(ops,stream,3)
        self.assertTrue(deployed.wait(2));self.assertEqual(ops.calls,[('drag','snoozebo',1)])
        stream.finish({'cells':['manteeny','dozy']+[None]*10});thread.join(2)
        self.assertEqual(errors,[]);self.assertEqual(ops.units,{1:'snoozebo'})
    def test_failure_and_terminal_updates_cannot_reopen_completed_stream(self):
        stream=FormationStream(2);stream.finish({'cells':['dozy',None]});stream.put(1,{'id':'rockwu'})
        self.assertEqual(stream.read()[:2],(['dozy',None],True))
        failed=FormationStream(2);failed.fail('bad image')
        with self.assertRaisesRegex(RuntimeError,'bad image'):failed.read()


class AutomaticImportUiTests(unittest.TestCase):
    def test_device_discovery_starts_once_and_editing_or_stop_cancels_pending_autostart(self):
        script=r'''
from pathlib import Path
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication
from lineup.backend import LineupBackend
from lineup.engine import FormationStream
app=QApplication([]);b=LineupBackend(discover=False);b._start=Mock()
stream=FormationStream(25);b.pending_auto=stream
b.finishDevices(b.generation,[{'title':'test','size':(540,998),'pid':1,'hwnd':123}],'')
b._start.assert_called_once_with(stream);assert b.pending_auto is None
b.pending_auto=FormationStream(25);b.stop();b._start.reset_mock()
b.finishDevices(b.generation,[{'title':'test','size':(540,998),'pid':1,'hwnd':123}],'')
b._start.assert_not_called()
b.pending_auto=FormationStream(25);b.setCell(0,'dozy');assert b.pending_auto is None
b.pending_auto=FormationStream(25);b.setColumns(3);assert b.pending_auto is None and len(b.cells)==12
b.pending_auto=FormationStream(12);b.finishDevices(b.generation,[],'device unavailable')
b._start.assert_not_called();assert 'device unavailable' in b.state['status']
b.close()
'''
        result=subprocess.run([sys.executable,'-c',script],cwd=ROOT,
            env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software'},capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

    def test_paste_starts_stream_and_stop_cancels_both_workers_without_device_input(self):
        script=r'''
import threading,time
from pathlib import Path
from unittest.mock import Mock,patch
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from lineup.backend import LineupBackend
from lineup.engine import FormationStream
from lineup.vision import Grid
app=QApplication([]);b=LineupBackend(discover=False);b.source_path=Path('validation/test-temp/stream-ui.png')
b.source_path.parent.mkdir(parents=True,exist_ok=True);b.entries=[{'hwnd':123}];b.overlay=Mock()
b.update(devices=['test'],deviceIndex=0)
recognized=threading.Event();started=threading.Event();release=threading.Event();streams=[];cancels=[]
def identify(*args,**kw):
 kw['cell_ready'](0,{'id':'dozy','score':.9,'candidates':[]},Grid((0,0,100,100),5,5))
 recognized.set();release.wait(3)
 if kw['cancel'].is_set():raise RuntimeError('已停止识别')
 return {'grid':Grid((0,0,100,100),5,5),'cells':['dozy']+[None]*24,'details':[]}
def run(hwnd,settings,stream,columns,cancel,publish):
 assert isinstance(stream,FormationStream);streams.append(stream);cancels.append(cancel)
 assert recognized.wait(2);assert stream.read()[0][0]=='dozy' and not stream.read()[1]
 started.set()
 while not cancel.is_set() and not stream.read()[1]:cancel.wait(.01)
 publish({'status':'已停止' if cancel.is_set() else '已上阵 1 只'})
with patch('lineup.vision.import_formation',side_effect=identify),patch('lineup.runner.run',side_effect=run) as worker:
 b.acceptImage(np.full((100,100,3),200,np.uint8));assert started.wait(2)
 QTest.qWait(50);b.poll();assert b.cells[0]=='dozy' and b.state['importing'] and b.state['running']
 b.stop();release.set()
 for _ in range(100):
  QTest.qWait(20);b.poll()
  if not b.state['importing'] and not b.state['running']:break
 assert cancels[0].is_set() and not b.worker.is_alive() and not b.deploy_worker.is_alive()
 assert not b.state['running'] and not b.state['importing'];assert worker.call_count==1
b.close();assert b.state['canClose']
'''
        result=subprocess.run([sys.executable,'-c',script],cwd=ROOT,
            env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software'},capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)


if __name__=='__main__':unittest.main()
