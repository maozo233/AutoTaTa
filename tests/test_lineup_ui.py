import os,subprocess,sys,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class LineupUiTests(unittest.TestCase):
    def test_export_dialog_cancel_and_saved_bundle(self):
        script=r'''
import tempfile,time
from unittest.mock import patch
from pathlib import Path
from zipfile import ZipFile
import numpy as np
from PySide6.QtCore import QPointF,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLineEdit
from autotata.app import Shell
from lineup.diagnostics import DiagnosticSession
base=Path('validation/test-temp');base.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(dir=base) as temp:
 root=Path(temp).resolve();s=Shell(discover=False,animations=False);s.nav.openLineup();w=s.window;b=s.nav.lineup
 b.source_path=root/'lineup-reference.png'
 diagnostic=DiagnosticSession(np.full((30,30,3),100,np.uint8),root=root);diagnostic.finish();b.diagnostics=diagnostic
 def find(n,name):
  if n.objectName()==name:return n
  for child in n.childItems():
   result=find(child,name)
   if result is not None:return result
 button=find(w.contentItem(),'lineupExportDiagnostics');assert button is not None and button.isEnabled()
 assert find(w.contentItem(),'lineupOpenDiagnostics') is not None
 with patch('PySide6.QtGui.QDesktopServices.openUrl',return_value=True) as opened:
  b.openDiagnostics();assert Path(opened.call_args.args[0].toLocalFile())==root/'logs/lineup-runs'
 b.exportDiagnostics();QTest.qWait(40);assert b.file_dialog.objectName()=='lineupExportDialog'
 b.file_dialog.reject();QTest.qWait(40);assert not b.state['exporting'] and b.export_worker is None
 b.exportDiagnostics();QTest.qWait(40)
 b.file_dialog.findChild(QLineEdit,'fileNameEdit').setText(str(root/'support.zip'));b.file_dialog.accept()
 for _ in range(150):
  time.sleep(.02);QTest.qWait(10);b.poll()
  if not b.state['exporting']:break
 if b.export_worker is not None:b.export_worker.join(2)
 b.poll()
 assert (root/'support.zip').is_file() and not b.state['exporting'],b.state
 with ZipFile(root/'support.zip') as archive:assert any(n.endswith('/source.png') for n in archive.namelist())
 assert 'support.zip' in b.state['diagnosticHint']
 b.update(running=True);QTest.qWait(30);assert not button.isEnabled()
 b.update(running=False);b.close();s.nav.close()
'''
        result=subprocess.run([sys.executable,'-c',script],cwd=ROOT,
            env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software','PYTHONUTF8':'1'},capture_output=True,text=True,encoding='utf8',errors='replace',timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

    def test_clipboard_progress_manual_correction_and_inactive_inputs(self):
        script=r'''
import threading,time
from pathlib import Path
from unittest.mock import Mock,patch
from PySide6.QtCore import QObject,Qt,QPointF
from PySide6.QtGui import QImage
from PySide6.QtQml import QQmlExpression
from PySide6.QtTest import QTest
from autotata.app import Shell
from tests.ui_helpers import popup_window
from lineup.vision import Grid
s=Shell(discover=False,animations=False);s.nav.openLineup();w=s.window;b=s.nav.lineup
b.source_path=Path('validation/test-temp/lineup-ui-reference.png');b.source_path.parent.mkdir(parents=True,exist_ok=True)
def find(n,name):
 if n.objectName()==name:return n
 for child in n.childItems():
  result=find(child,name)
  if result is not None:return result
def click(n):
 p=n.mapToItem(w.contentItem(),QPointF(n.width()/2,n.height()/2));QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,p.toPoint())
gate=threading.Event()
def recognize(*args,**kw):
 gate.wait(3)
 return {'grid':Grid((47,44,295,295),5,5),'cells':[None]*6+['serrabloom']+[None]*18,'details':[]}
s.application.clipboard().setImage(QImage('tests/fixtures/lineup/reference-grid.png'))
w.requestActivate();QTest.qWait(40)
shot=find(w.contentItem(),'lineupScreenshot')
assert shot and shot.isEnabled() and shot.width()==80
with patch('fishing.windows.start_screen_clip') as send:
 click(shot);QTest.qWait(30)
 send.assert_called_once_with()
 assert 'Ctrl+V' in b.state['status']
 with patch.object(b,'worker',Mock(is_alive=lambda:True)):
  for busy in ('running','importing'):
   b.update(**{busy:True});QTest.qWait(40)
   assert not shot.isEnabled()
   b.screenshot();assert send.call_count==1
   b.update(**{busy:False})
with patch('fishing.windows.start_screen_clip',side_effect=OSError('test unavailable')):
 b.screenshot();assert 'Win+Shift+S' in b.state['status']
with patch('lineup.vision.import_formation',side_effect=recognize):
 QTest.keyClick(w,Qt.Key_V,Qt.ControlModifier);QTest.qWait(60)
 assert b.state['importing'] and b.state['source'],b.state
 assert find(w.contentItem(),'lineupRecognizing').isVisible()
 assert QQmlExpression(s.engine.rootContext(),find(w.contentItem(),'lineupSource'),'status === 1').evaluate()
 assert not find(w.contentItem(),'lineupStart').isEnabled()
 gate.set()
 for _ in range(40):
  QTest.qWait(30)
  if not b.state['importing']:break
 assert b.cells[6]=='serrabloom' and not b.state['running']
 assert not find(w.contentItem(),'lineupRecognizing').isVisible()
click(find(w.contentItem(),'lineupTile6'));QTest.qWait(40)
editor=w.findChild(QObject,'lineupEditor');assert editor.property('visible')
native=popup_window(editor);assert native is not w
assert native.transientParent() is w
assert len(b.search('海兔姬'))==1
b.setCell(6,'bubbit');assert b.state['cells'][6]['stage']==2
QTest.keyClick(native,Qt.Key_Escape);QTest.qWait(30)
assert not editor.property('visible')
s.application.clipboard().clear();b.pasteImage();assert '没有图片' in b.state['status']
import numpy as np
with patch.object(b,'recognize'):
 b.acceptImage(np.full((64,64),130,np.uint8));assert b.image.shape==(64,64,3)
 image=QImage(64,64,QImage.Format_ARGB32);image.fill(Qt.transparent)
 s.application.clipboard().setImage(image);b.pasteImage();assert b.image[0,0].tolist()==[245,245,245]
assert not s.errors,s.errors
assert w.property('pageTheme').property('canvas').name()=='#edf4e6'
b.setColumns(3);QTest.qWait(30)
assert b.state['rows']==4 and len(b.state['cells'])==12
assert find(w.contentItem(),'lineupTile11') is not None
assert find(w.contentItem(),'lineupTile12') is None
assert QQmlExpression(s.engine.rootContext(),find(w.contentItem(),'lineupGridPicker'),'model[1] === "3 × 4"').evaluate()
b.setCell(12,'dozy');assert len(b.cells)==12
b.setColumns(5);assert b.state['rows']==5 and len(b.cells)==25
b.update(autoPending=True);QTest.qWait(30)
assert find(w.contentItem(),'lineupStop').isEnabled()
assert not find(w.contentItem(),'lineupStart').isEnabled()
b.stop();assert not b.state['autoPending']
b.close();s.nav.close()
'''
        result=subprocess.run([sys.executable,'-c',script],cwd=ROOT,
            env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software'},capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
