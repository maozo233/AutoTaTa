"""Actual shared controls, native popup geometry, dismissal and common grip."""
import os,subprocess,sys,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=r'''
from autotata.app import Shell
from PySide6.QtCore import QObject,QMetaObject,QPoint,QPointF,Qt
from PySide6.QtQml import QQmlExpression,QQmlEngine
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from tests.ui_helpers import find_item,popup_window,click_item
from unittest.mock import Mock,patch
s=Shell(discover=False,animations=False)
grip=None
for feature,name in [('treasure','treasureDevicePicker'),('rafting','raftingModePicker'),('lineup','lineupModePicker'),('fishing','modePicker')]:
 getattr(s.nav,'open'+feature.capitalize())();QTest.qWait(80)
 w=s.nav.fishing.window if feature=='fishing' else s.window
 if feature=='treasure':s.treasure.live['devices']=['Device A','Device B'];s.treasure.changed.emit()
 icon=find_item(w,'resizeGripIcon');mark=find_item(w,'resizeGrip')
 geometry=(mark.width(),mark.height(),icon.property('source').toString())
 if grip is None:grip=geometry
 assert geometry==grip and geometry[:2]==(24,24),geometry
 for factor in (.5,.75,1):
  if feature=='fishing':s.nav.fishing.backend.resizeTo(factor)
  else:w.setProperty('treasureZoom',factor)
  QTest.qWait(220)
  p=find_item(w,name)
  for repeat in range(2):
   expr=QQmlExpression(QQmlEngine.contextForObject(p),p,'popup.open()');expr.evaluate();QTest.qWait(140)
   assert not expr.hasError(),expr.error().toString()
   pop=w.findChild(QObject,name+'Popup')
   try:native=popup_window(pop)
   except AssertionError:
    raise AssertionError((feature,factor,repeat,pop.property('visible'),[(a.metaObject().className(),a.geometry(),a.isVisible()) for a in QGuiApplication.allWindows()]))
   left=p.mapToGlobal(QPointF(0,0));right=p.mapToGlobal(QPointF(p.width(),p.height()))
   assert native is not w and abs(native.width()-(right.x()-left.x()))<=1.5,(feature,factor,native.geometry(),left,right)
   assert abs(native.x()+native.width()/2-(left.x()+right.x())/2)<=1.5,(feature,factor,native.geometry(),left,right)
   assert native.height()>20
   QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,QPoint(w.width()-2,w.height()//2));QTest.qWait(120)
   assert not pop.property('visible'),(feature,'outside click did not close')
 if feature=='fishing':
  b=s.nav.fishing.backend;b.persist=lambda:None;b.confirmStart=Mock()
  b.setMode=Mock()
  p=find_item(w,name);expr=QQmlExpression(QQmlEngine.contextForObject(p),p,'popup.open()');expr.evaluate();QTest.qWait(140)
  pop=w.findChild(QObject,name+'Popup');native=popup_window(pop);zoom=pop.property('uiScale')
  QTest.mouseClick(native,Qt.LeftButton,Qt.NoModifier,QPoint(native.width()//2,round((4+28*1.5)*zoom)));QTest.qWait(120)
  assert p.property('currentIndex')==1 and not pop.property('visible')
  b.setMode.assert_called_once_with(1)
  b.warning.emit('test','short');d=w.findChild(QObject,'warningDialog')
 else:
  s.nav.message.emit('short');d=w.findChild(QObject,'noticeDialog')
 QTest.qWait(120);native=popup_window(d)
 assert abs(native.geometry().center().x()-w.geometry().center().x())<2
 assert abs(native.geometry().center().y()-w.geometry().center().y())<2
 QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,QPoint(w.width()-2,w.height()//2));QTest.qWait(100)
 assert not d.property('visible')
 if feature=='fishing':b.warning.emit('test','short')
 else:s.nav.message.emit('short')
 QTest.qWait(100);QMetaObject.invokeMethod(d,'accept');QTest.qWait(100)
 assert not d.property('visible')
 if feature=='lineup':
  editor=w.findChild(QObject,'lineupEditor');from PySide6.QtCore import Q_ARG
  QMetaObject.invokeMethod(editor,'openCell',Q_ARG('QVariant',6));QTest.qWait(120)
  native=popup_window(editor);assert native is not w
  QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,QPoint(w.width()-2,w.height()//2));QTest.qWait(100)
  assert not editor.property('visible')
  b=s.nav.lineup;b.chooseImage();QTest.qWait(100)
  chooser=b.file_dialog;assert chooser is not None and chooser.isVisible()
  assert chooser.isWindow()
  QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,QPoint(w.width()-2,8));QTest.qWait(80)
  assert b.file_dialog is None
  b.chooseImage();QTest.qWait(80);chooser=b.file_dialog
  from pathlib import Path
  with patch.object(b,'loadImage') as load:
   from PySide6.QtWidgets import QLineEdit
   chooser.findChild(QLineEdit,'fileNameEdit').setText(str(Path('tests/fixtures/lineup/reference-grid.png').resolve()))
   chooser.accept();QTest.qWait(80)
   load.assert_called_once();assert b.file_dialog is None
 if feature=='fishing':s.nav.back()
 else:s.nav.returnHome()
assert not s.errors,s.errors
assert not s.nav.fishing.qml_errors,s.nav.fishing.qml_errors
for manager in (s.popup_windows,s.nav.fishing.popup_windows):
 for frame in manager.frames.values():
  state=frame.snapshot()
  if state['enabled']:assert state['frameStyles'] and state['nativeRendering'] and not state['errors'],state
s.nav.close()
'''


class SharedPopupTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='win32','Native Windows verification')
    def test_native_frame_does_not_depend_on_popup_opened_notification(self):
        script=r'''
from autotata.app import Shell
from PySide6.QtCore import QObject,QMetaObject,Q_ARG
from PySide6.QtTest import QTest
from tests.ui_helpers import popup_window
import ctypes
from ctypes import wintypes
s=Shell(discover=False,lineup_only=True,animations=False)
QTest.qWait(100)
editor=s.window.findChild(QObject,'lineupEditor')
editor.blockSignals(True)
assert QMetaObject.invokeMethod(editor,'openCell',Q_ARG('QVariant',6))
QTest.qWait(120)
native=popup_window(editor)
frame=s.window_frame;handle=int(native.winId());rendered=wintypes.BOOL()
frame.dwm.DwmGetWindowAttribute(handle,1,ctypes.byref(rendered),ctypes.sizeof(rendered))
assert rendered.value and frame.user.GetWindowLongPtrW(handle,-16)&0x00C00000==0x00C00000
editor.blockSignals(False);QMetaObject.invokeMethod(editor,'close');QTest.qWait(40)
s.nav.close()
'''
        result=subprocess.run([sys.executable,'-c',script],cwd=ROOT,capture_output=True,text=True,timeout=20,
            env={k:v for k,v in {**os.environ,'QT_QPA_PLATFORM':'windows'}.items() if k!='QT_QUICK_BACKEND'})
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
    def check(self,platform):
        result=subprocess.run([sys.executable,'-c',SCRIPT],cwd=ROOT,
            env={**os.environ,'QT_QPA_PLATFORM':platform,'QT_QUICK_BACKEND':'software'} if platform=='offscreen' else
                {k:v for k,v in {**os.environ,'QT_QPA_PLATFORM':platform}.items() if k!='QT_QUICK_BACKEND'},
            capture_output=True,text=True,timeout=40)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
    def test_scaled_dropdowns_independent_dialogs_and_dismissal(self):self.check('offscreen')
    @unittest.skipUnless(sys.platform=='win32','Native Windows verification')
    def test_native_windows_across_four_features(self):self.check('windows')
