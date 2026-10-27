import logging
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from fishing.log_policy import BoundedSessionHandler,LogMaintenance,MAX_LOG_BYTES,SESSION_BYTES,NATIVE_BYTES,trim_tail,log_cursor,native_log_lock
from fishing.maa_input import new_input_failure

class LogPolicyTests(unittest.TestCase):
    def test_utf8_rotation_bounds_current_and_previous(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'session.log';h=BoundedSessionHandler(p,512)
            try:
                for i in range(100):h.handle(logging.LogRecord('test',20,'',0,'控鱼 第%s次记录',(i,),None))
                for path in (p,Path(str(p)+'.1')):
                    self.assertLessEqual(path.stat().st_size,512)
                    path.read_text(encoding='utf-8')
                self.assertIn('第99次',p.read_text(encoding='utf-8'))
                self.assertFalse(Path(str(p)+'.2').exists())
            finally:h.close()
    def test_oversized_record_cannot_exceed_limit(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'session.log';h=BoundedSessionHandler(p,256)
            try:
                h.handle(logging.LogRecord('test',20,'',0,'鱼'*1000,(),None))
                self.assertLessEqual(p.stat().st_size,256)
                self.assertIn('[truncated]',p.read_text(encoding='utf-8'))
            finally:h.close()
    def test_existing_native_and_session_backups_share_budget(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ('logs/session.log','logs/session.log.1','maa/debug/maafw.log','build/maa/debug/maafw.log'):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'old record\n'*400000)
            (root/'maa/debug/maafw.bak.old.log').write_bytes(b'x'*1000)
            image=root/'logs/last-stop.png';image.write_bytes(b'keep screenshot')
            settings=root/'settings.json';settings.write_text('keep settings')
            LogMaintenance(root).sweep()
            files=[root/n for n in ('logs/session.log','logs/session.log.1','maa/debug/maafw.log','build/maa/debug/maafw.log')]
            self.assertLess(sum(p.stat().st_size for p in files),MAX_LOG_BYTES)
            self.assertFalse((root/'maa/debug/maafw.bak.old.log').exists())
            self.assertEqual(image.read_bytes(),b'keep screenshot')
            self.assertEqual(settings.read_text(),'keep settings')
    def test_appending_open_stream_after_trim_does_not_create_sparse_hole(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'maa.log';p.write_bytes(b'old\n'*1000)
            with p.open('ab') as writer:
                trim_tail(p,100);writer.write(b'new record\n');writer.flush()
            self.assertLessEqual(p.stat().st_size,111)
            self.assertTrue(p.read_bytes().endswith(b'new record\n'))
            self.assertNotIn(b'\x00',p.read_bytes())
    def test_current_error_cursor_survives_trim_without_including_old_errors(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'maa.log'
            p.write_text(f'[ERR][Px{os.getpid()}] still occluded after being raised\n'+'old\n'*500,encoding='utf-8')
            cursor=log_cursor(p);trim_tail(p,200)
            with p.open('a',encoding='utf-8') as stream:stream.write(f'[ERR][Px{os.getpid()}] the target point is outside the desktop\n')
            with patch('fishing.maa_input.maa_log_path',return_value=p):
                reason=new_input_failure(cursor)
            self.assertIn('超出桌面',reason)
            self.assertNotIn('遮挡',reason)
    def test_cleanup_waits_for_input_diagnosis_guard(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);service=LogMaintenance(root);done=threading.Event()
            with native_log_lock:
                worker=threading.Thread(target=lambda:(service.sweep(),done.set()));worker.start()
                self.assertFalse(done.wait(.05))
            worker.join(1);self.assertTrue(done.is_set())
    def test_rename_failure_still_bounds_and_records_latest(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'session.log';h=BoundedSessionHandler(p,256)
            try:
                h.handle(logging.LogRecord('test',20,'',0,'old'*60,(),None))
                with patch.object(h,'doRollover',side_effect=PermissionError('old app open')):
                    h.handle(logging.LogRecord('test',20,'',0,'new'*60,(),None))
                self.assertLessEqual(p.stat().st_size,256)
                self.assertTrue(p.read_text().endswith('new'*60+'\n'))
            finally:h.close()
