"""Retained evidence, portable ZIP contents, and failure/action screenshots."""
import json,logging,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from zipfile import ZipFile
import cv2,numpy as np
from lineup.diagnostics import DiagnosticSession,records,export_bundle
from lineup.engine import Settings
from tests import test_lineup as helpers

TEMP=Path(__file__).resolve().parents[1]/'validation/test-temp'
TEMP.mkdir(parents=True,exist_ok=True)


class DiagnosticBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=TEMP);self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.sessions=[]
        self.addCleanup(lambda:[s.finish() for s in self.sessions])
    def session(self,level=80):
        session=DiagnosticSession(np.full((25,30,3),level,np.uint8),{'mode':'mumu_sdk','adb_path':'private path'},root=self.root)
        self.sessions.append(session);return session
    def test_each_run_keeps_its_original_and_only_twenty_owned_runs_remain(self):
        foreign=self.root/'logs/lineup-runs/run-000-foreign';foreign.mkdir(parents=True)
        (foreign/'manifest.json').write_text('{"schema":"unrelated"}')
        for i in range(23):
            session=self.session(i);session.stage('recognition','completed',cells=['dozy']);session.finish()
        saved=records(self.root)
        self.assertEqual(len(saved),20);self.assertTrue(foreign.exists())
        self.assertFalse(self.sessions[0].path.exists())
        self.assertTrue(np.all(cv2.imread(str(self.sessions[-1].path/'source.png'))==22))
        self.assertNotIn('adb_path',saved[0][1]['settings'])
    def test_export_after_restart_contains_all_evidence_and_excludes_unrelated_files(self):
        session=self.session();session.capture(np.full((40,35,3),170,np.uint8),'game-failure',error='unknown unit')
        session.stage('recognition','partial',cells=['?'],details=[{'id':'?','score':.5}])
        session.stage('deployment','failed',error='unknown unit')
        logging.getLogger('lineup').warning('diagnostic test log marker')
        session.finish()
        (self.root/'secret.env').write_text('never include this')
        (self.root/'lineup-reference.png').write_bytes((session.path/'source.png').read_bytes())
        path=export_bundle(self.root/'support.zip',root=self.root)
        with ZipFile(path) as archive:
            names=archive.namelist();prefix='runs/'+session.path.name+'/'
            self.assertIn(prefix+'source.png',names);self.assertIn(prefix+'game-failure.png',names)
            self.assertIn('legacy/lineup-reference.png',names);self.assertNotIn('secret.env',names)
            self.assertIn('diagnostic test log marker',archive.read(prefix+'session.log').decode('utf8'))
            report=json.loads(archive.read('bundle.json'));self.assertEqual(report['sessions'][0]['status'],'failed')
            self.assertEqual(report['readErrors'],[])
            self.assertEqual(archive.read(prefix+'source.png'),(session.path/'source.png').read_bytes())
    def test_fixed_screenshot_slots_keep_last_action_and_failure_without_unbounded_frames(self):
        session=self.session()
        for i in range(8):session.capture(np.full((30,30,3),i,np.uint8),'game-before-action',index=i)
        session.capture(np.full((30,30,3),99,np.uint8),'game-failure')
        self.assertEqual(len(list(session.path.glob('*.png'))),3)
        self.assertTrue(np.all(cv2.imread(str(session.path/'game-before-action.png'))==7))
        self.assertTrue(np.all(cv2.imread(str(session.path/'game-failure.png'))==99))
    def test_export_failure_preserves_the_existing_archive(self):
        target=self.root/'support.zip';target.write_bytes(b'existing')
        with patch('lineup.diagnostics.ZipFile',side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):export_bundle(target,root=self.root)
        self.assertEqual(target.read_bytes(),b'existing');self.assertEqual(list(self.root.glob('*.pending')),[])


class DiagnosticActionTests(unittest.TestCase):
    operations=helpers.ObservationGuardTests.operations
    def test_unknown_withdrawal_saves_the_actual_before_and_after_frames(self):
        with tempfile.TemporaryDirectory(dir=TEMP) as folder:
            diagnostic=DiagnosticSession(root=folder)
            try:
                ops=self.operations();ops.diagnostics=diagnostic;obs=ops.observation;obs.count=1
                ops.guard=Mock(return_value=obs)
                with patch('lineup.runner.occupied_cell',return_value=True):ops.withdraw_unrecognized(0,1)
                ops.frame[:]=180;obs.count=0;ops.snapshot=Mock(return_value=obs)
                with patch('lineup.runner.occupied_cell',return_value=False):ops.wait_count(0)
                self.assertTrue(np.all(cv2.imread(str(diagnostic.path/'game-before-action.png'))==120))
                self.assertTrue(np.all(cv2.imread(str(diagnostic.path/'game-after-action.png'))==180))
                events=[json.loads(s) for s in (diagnostic.path/'events.jsonl').read_text('utf8').splitlines()]
                self.assertEqual([s['count'] for s in events if s['event']=='screenshot'],[1,0])
            finally:diagnostic.finish()
    def test_runner_exception_captures_failure_frame_and_traceback(self):
        from lineup.runner import run
        with tempfile.TemporaryDirectory(dir=TEMP) as folder:
            diagnostic=DiagnosticSession(root=folder);frame=np.full((40,30,3),91,np.uint8)
            capture=Mock();capture.read.return_value=(frame,time.monotonic(),1,(30,40));mouse=Mock()
            publish=Mock();publish.diagnostics=diagnostic
            try:
                with patch('lineup.runner.connect',return_value=(capture,mouse)),patch('lineup.runner.execute',side_effect=RuntimeError('test failure')):
                    run(123,Settings(),['dozy']+[None]*24,5,threading.Event(),publish)
                self.assertTrue((diagnostic.path/'game-failure.png').is_file())
                self.assertTrue(np.all(cv2.imread(str(diagnostic.path/'game-final.png'))==91))
                self.assertIn('test failure',diagnostic.data['stages']['deployment']['traceback'])
                capture.close.assert_called_once();mouse.close.assert_called_once()
            finally:diagnostic.finish()


if __name__=='__main__':unittest.main()
