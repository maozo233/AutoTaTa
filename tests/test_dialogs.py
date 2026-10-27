"""Check shared dialogs retain their actions and stay centered after scaling."""
import os,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class DialogTests(unittest.TestCase):
    def test_shared_modals(self):
        code=r"""
from tests.test_treasure_resize import SETUP
exec(SETUP)
from PySide6.QtCore import QMetaObject
from unittest.mock import Mock
out=ROOT/'validation/dialogs-0.1.9';out.mkdir(exist_ok=True,parents=True)
def opened(d,name):
 QTest.qWait(60)
 assert d.property('visible'),name
 c=d.property('contentItem');cp=c.mapToItem(w.contentItem(),QPointF(c.width()/2,c.height()/2))
 assert abs(cp.x()-w.width()/2)<2 and abs(cp.y()-w.height()/2)<2,(name,cp,w.size())
 assert d.property('height')*d.property('scale')<w.height(),name
 w.grabWindow().save(str(out/(name+'.png')))
s.nav.returnHome();QTest.qWait(60)
w.grabWindow().save(str(out/'home.png'))
s.nav.message.emit('测试提示')
d=w.findChild(QObject,'noticeDialog');opened(d,'notice')
QTest.keyClick(popup_window(d),Qt.Key_Escape);assert not d.property('visible')
s.nav.openTreasure();QTest.qWait(60)
s.treasure.calculate=Mock();s.treasure.mark(0,2)
d=w.findChild(QObject,'clearMarksDialog');QMetaObject.invokeMethod(d,'open');opened(d,'clear')
QMetaObject.invokeMethod(d,'reject');assert s.treasure.state['cells'][0]==2
QMetaObject.invokeMethod(d,'open');QMetaObject.invokeMethod(d,'accept');assert s.treasure.state['cells'][0]==0
size=item('sizeInput');size.setProperty('text','6')
d=w.findChild(QObject,'boardSizeDialog');QMetaObject.invokeMethod(d,'open');opened(d,'size')
QMetaObject.invokeMethod(d,'reject');assert s.treasure.state['size']==5 and size.property('text')=='5'
QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,center(item('treasureRow1')))
d=w.findChild(QObject,'treasureDialog');opened(d,'add')
item('treasureWidthInput').setProperty('text','9')
QMetaObject.invokeMethod(d,'accept');QTest.qWait(30)
assert d.property('visible') and d.property('errorText')
QTest.keyClick(popup_window(d),Qt.Key_Escape);assert not d.property('visible')
s.nav.openFishing();QTest.qWait(60);w=s.nav.fishing.window
s.nav.fishing.backend.persist=lambda:None
s.nav.fishing.backend.confirmStart=Mock()
s.nav.fishing.backend.warning.emit('窗口提示','当前窗口较小，请检查尺寸。')
d=w.findChild(QObject,'warningDialog');opened(d,'fishing')
QMetaObject.invokeMethod(d,'accept')
assert not d.property('visible')
s.nav.fishing.backend.warning.emit('较长提示','请检查模拟器窗口和连接。'*80)
opened(d,'long-warning');QTest.keyClick(popup_window(d),Qt.Key_Escape)
assert not d.property('visible')
assert not s.errors,s.errors
assert not s.nav.fishing.qml_errors,s.nav.fishing.qml_errors
s.treasure.close();s.nav.fishing.backend.timer.stop()
"""
        code="from pathlib import Path\nROOT=Path("+repr(str(ROOT))+")\n"+code
        result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software'},capture_output=True,text=True,timeout=25)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
