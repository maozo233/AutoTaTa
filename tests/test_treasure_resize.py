"""Exercise real QML geometry and input after proportional resizing."""
import os,subprocess,sys,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SETUP="""
from PySide6.QtCore import QObject,QPoint,QPointF,Qt
from PySide6.QtTest import QTest
from PySide6.QtQml import QQmlExpression,QQmlEngine
from autotata.app import Shell
from tests.ui_helpers import find_item,click_item,popup_window
s=Shell(discover=False,animations=False)
s.nav.openTreasure()
w=s.window
QTest.qWait(80)
p=w.findChild(QObject,'treasurePage')
def item(name,node=None):
    if node is None:return find_item(w,name)
    node=node or w.contentItem()
    if node.objectName()==name:return node
    for child in node.childItems():
        found=item(name,child)
        if found is not None:return found
def center(node):
    return node.mapToItem(w.contentItem(),QPointF(node.width()/2,node.height()/2)).toPoint()
def full():
    footer=item('treasureFooter')
    end=footer.mapToItem(w.contentItem(),QPointF(footer.width(),footer.height()))
    assert end.x()<=w.width()+1 and end.y()<=w.height()-8,(end,w.size())
    area=w.screen().availableGeometry()
    assert w.width()<=area.width() and w.height()<=area.height()
    assert area.contains(w.geometry()),(area,w.geometry())
    assert not s.errors,s.errors
def drag(dx,dy):
    start=center(item('treasureResizeArea'))
    QTest.mousePress(w,Qt.LeftButton,Qt.NoModifier,start)
    QTest.mouseMove(w,start+QPoint(dx,dy),20)
    QTest.mouseRelease(w,Qt.LeftButton,Qt.NoModifier,start+QPoint(dx,dy))
    QTest.qWait(40)
"""

class TreasureResizeTests(unittest.TestCase):
    def check(self,code):
        result=subprocess.run([sys.executable,'-c',SETUP+code],cwd=ROOT,
            env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software'},
            capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
    def test_layout_five_rows_and_resizing(self):
        self.check("""
full()
assert w.property('baseWidth')==800
assert item('treasureList').height()==282
assert item('treasureRow4') is not None
s.treasure.live['status']='请重新识别'+('较长提示'*100)
s.treasure.changed.emit();QTest.qWait(50)
full()
before=w.property('visualZoom');drag(-35,-35)
assert w.property('visualZoom')<before
full()
s.nav.returnHome()
assert w.property('baseWidth')==615
s.treasure.close()
""")
    def test_scaled_cell_popup_and_add_dialog(self):
        self.check("""
w.setProperty('treasureZoom',.5);QTest.qWait(40)
before=w.property('visualZoom');drag(55,50)
assert w.property('visualZoom')>before
QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,center(item('treasureCell0')))
QTest.qWait(80)
popup=w.findChild(QObject,'cellActionsPopup')
assert popup.property('visible')
assert abs(popup.property('uiScale')-w.property('visualZoom'))<.0001
click_item(w,item('cellAction1'))
assert s.treasure.state['cells'][0]==2
s.treasure.undo();assert s.treasure.state['cells'][0]==0
QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,center(item('treasureRow1')))
QTest.qWait(80)
dialog=w.findChild(QObject,'treasureDialog')
assert dialog.property('visible')
assert abs(dialog.property('uiScale')-w.property('visualZoom'))<.0001
content=dialog.property('contentItem')
cp=content.mapToItem(w.contentItem(),QPointF(content.width()/2,content.height()/2))
assert abs(cp.x()-w.width()/2)<2 and abs(cp.y()-w.height()/2)<2,(cp,w.size())
click_item(w,item('saveTreasureButton'))
QTest.qWait(80)
assert not dialog.property('visible')
assert s.treasure.state['shapes'][-1]==[1,1,1]
assert not s.errors,s.errors
s.treasure.close()
""")

    def test_full_list_still_adds_and_confirmation_does_not_stop_recognition(self):
        self.check("""
from unittest.mock import Mock
from PySide6.QtCore import QMetaObject
s.treasure.calculate=Mock()
s.treasure._state['shapes']=[[1,1,1],[1,2,1],[1,3,1],[1,4,1],[2,2,1]]
s.treasure.live.update(running=True,autoConfig=True,derived=True,configurationWarning='宝物尺寸为估算，请核对尺寸与数量')
s.treasure.changed.emit();QTest.qWait(60)
view=item('treasureList')
QQmlExpression(QQmlEngine.contextForObject(view),view,'positionViewAtEnd()').evaluate();QTest.qWait(60)
blank=item('treasureRow5');assert blank is not None
QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,center(blank));QTest.qWait(60)
dialog=w.findChild(QObject,'treasureDialog');assert dialog.property('visible')
QMetaObject.invokeMethod(dialog,'accept');QTest.qWait(60)
assert len(s.treasure.state['shapes'])==6
auto_before=s.treasure.live['autoConfig']
QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,center(item('confirmTreasureButton')));QTest.qWait(40)
assert s.treasure.state['treasuresConfirmed'] and not s.treasure.state['configurationWarning']
assert s.treasure.live['running'] and s.treasure.live['autoConfig']==auto_before
badge=item('boardWarningBadge');cell=item('treasureCell4')
br=badge.mapToItem(w.contentItem(),QPointF(badge.width(),0))
cr=cell.mapToItem(w.contentItem(),QPointF(cell.width(),0))
assert abs(br.x()-cr.x())<1,(br,cr)
assert not s.errors,s.errors
s.treasure.close()
""")

if __name__=='__main__':unittest.main()
