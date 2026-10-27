"""Actual popup text, edge selection, scrolling and editable-device input."""
import os,subprocess,sys,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=r'''
import os
from autotata.app import Shell
from PySide6.QtCore import QObject,QPointF,Qt
from PySide6.QtQml import QQmlEngine,QQmlExpression
from PySide6.QtTest import QTest
from tests.ui_helpers import find_item,popup_window,click_item
from unittest.mock import Mock,patch
s=Shell(discover=False,animations=False)
names=['MuMu 安卓设备 A · 539×998 · PID 100',
       'MuMu 安卓设备 B · 900×1600 · PID 200',
       'MuMu 安卓设备 · 很长的窗口名称以及设备信息，需要完整显示而不是被上下留白裁切 · PID 300']
checks=0
def expression(p,code):
 e=QQmlExpression(QQmlEngine.contextForObject(p),p,code);value=e.evaluate()
 assert not e.hasError(),e.error().toString()
 return value[0]
for feature in ('treasure','rafting','lineup','fishing'):
 getattr(s.nav,'open'+feature.capitalize())();QTest.qWait(70)
 w=s.nav.fishing.window if feature=='fishing' else s.window
 b=getattr(s.nav,feature)
 if feature=='fishing':b=b.backend
 b.persist=Mock()
 if hasattr(b,'refresh'):b.refresh=Mock()
 if feature=='treasure':
  b.devices=[{}, {}, {}];b.live.update(devices=names,deviceIndex=0);b.changed.emit()
  cases=[('treasureDevicePicker','chooseDevice')]
 else:
  b.entries=[{}, {}, {}];b.setMode(0)
  b.update(devices=names,deviceIndex=0,deviceText=names[0],refreshing=False)
  cases={'rafting':[('raftingModePicker','setMode'),('raftingDevicePicker','selectDevice')],
         'lineup':[('lineupModePicker','setMode'),('lineupDevicePicker','selectDevice'),('lineupGridPicker','setColumns')],
         'fishing':[('modePicker','setMode'),('devicePicker','selectDevice'),('multiplierPicker','setValue')]}[feature]
 for factor in (.5,.75,1):
  if feature=='fishing':b.resizeTo(factor)
  else:w.setProperty('treasureZoom',factor)
  w.requestActivate();QTest.qWait(190)
  for name,method in cases:
   if name=='devicePicker':b.setMode(0)
   p=find_item(w,name);assert p and p.isEnabled(),(feature,name)
   for index in (int(p.property('count'))-1,0):
    with patch.object(b,method,wraps=getattr(b,method)) as activated:
     if os.environ.get('QT_QPA_PLATFORM')=='offscreen':expression(p,'popup.open()')
     else:click_item(w,p)
     QTest.qWait(110)
     pop=w.findChild(QObject,name+'Popup');assert pop.property('visible'),(feature,name,'body did not open popup')
     native=popup_window(pop)
     left=p.mapToGlobal(QPointF(0,0));right=p.mapToGlobal(QPointF(p.width(),0))
     assert abs(native.width()-(right.x()-left.x()))<=1.5,(feature,name,factor,native.width(),left,right)
     assert abs(native.x()+native.width()/2-(left.x()+right.x())/2)<=1.5
     expression(p,f'popup.contentItem.positionViewAtIndex({index},ListView.Contain)');QTest.qWait(30)
     item=find_item(w,'pickerOption'+str(index));assert item is not None,(feature,name,index)
     text=item.property('contentItem')
     assert text.height()>=text.property('implicitHeight')-.5,(feature,name,factor,text.height(),text.property('implicitHeight'))
     assert text.property('font').pixelSize()>=10
     assert item.height()>=24 and item.property('topPadding')==0 and item.property('bottomPadding')==0
     if name.endswith('DevicePicker') or name=='devicePicker':
      assert text.property('text')==names[index]
      if index==2 and factor==.5:assert text.property('lineCount')>1
     width=item.width()
     point=item.mapToGlobal(QPointF(item.width()-1,item.height()/2)).toPoint()-native.position()
     QTest.mouseMove(native,point);QTest.qWait(20)
     assert item.width()==width,(feature,name,'hover changed hit area')
     QTest.mouseClick(native,Qt.LeftButton,Qt.NoModifier,point);QTest.qWait(110)
     assert not pop.property('visible'),(feature,name,'selection did not close popup')
     assert p.property('currentIndex')==index,(feature,name,index,p.property('currentIndex'))
     assert activated.call_count==1,(feature,name,activated.call_args_list)
     checks+=1
 if feature=='fishing':
  # Editable ADB entry keeps typing, while read-only device text lets body
  # clicks reach the combo box rather than swallowing the mouse event.
  b.setMode(2);QTest.qWait(30);p=find_item(w,'devicePicker')
  w.requestActivate();QTest.qWait(30)
  child=p.property('contentItem');assert child.isEnabled()
  child.forceActiveFocus();QTest.keyClick(w,Qt.Key_A,Qt.ControlModifier)
  with patch.object(b,'setAddress') as accepted:
   for character in '127.0.0.1:16384':QTest.keyClick(w,Qt.Key(ord(character)))
   QTest.keyClick(w,Qt.Key_Return);QTest.qWait(40)
   accepted.assert_called_once_with('127.0.0.1:16384')
  s.nav.back()
 else:s.nav.returnHome()
assert checks==54,checks
assert not s.errors,s.errors
assert not s.nav.fishing.qml_errors,s.nav.fishing.qml_errors
print('54 dropdown selections passed')
s.nav.close()
'''


class PickerInteractionTests(unittest.TestCase):
    def check(self,platform):
        env={**os.environ,'QT_QPA_PLATFORM':platform}
        if platform=='offscreen':env['QT_QUICK_BACKEND']='software'
        else:env.pop('QT_QUICK_BACKEND',None)
        result=subprocess.run([sys.executable,'-c',SCRIPT],cwd=ROOT,env=env,capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
    def test_all_dropdowns_text_edge_selection_and_scroll_at_small_sizes(self):self.check('offscreen')
    @unittest.skipUnless(sys.platform=='win32','Native Windows verification')
    def test_native_dropdown_selection_and_text_at_small_sizes(self):self.check('windows')
