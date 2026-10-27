from tests.qt_ui_case import QtUiCase
SETUP="""
from PySide6.QtCore import QObject,QPoint,QPointF,Qt
from PySide6.QtTest import QTest
from fishing.gpu_app import GpuApp
from unittest.mock import Mock
app=GpuApp(discover=False,hotkeys=False);app.backend.timer.stop();app.backend.persist=Mock()
w=app.window
QTest.qWait(60)
def drag(dx,dy):
 grip=w.findChild(QObject,'resizeGrip')
 start=grip.mapToItem(w.contentItem(),QPointF(grip.width()/2,grip.height()/2)).toPoint()
 QTest.mousePress(w,Qt.LeftButton,Qt.NoModifier,start)
 QTest.mouseMove(w,start+QPoint(dx,dy),30)
 QTest.mouseRelease(w,Qt.LeftButton,Qt.NoModifier,start+QPoint(dx,dy))
 QTest.qWait(60)
def ratio():
 assert abs(w.width()/w.height()-w.property('baseWidth')/w.property('baseHeight'))<.003
 assert not app.qml_errors,app.qml_errors
"""
class ResizeTests(QtUiCase):
    def test_dragging_either_axis_preserves_ratio(self):
        self.run_qt(SETUP+"""
for dx,dy in ((40,0),(0,40),(30,-10),(-10,0)):
 app.backend.resizeTo(.6);QTest.qWait(40);before=w.property('visualZoom')
 drag(dx,dy);ratio()
 assert (w.property('visualZoom')>before)==(max(dx,dy)>0)
""")
    def test_can_shrink_large_window_to_content_minimum(self):
        self.run_qt(SETUP+"""
app.backend.resizeTo(1);QTest.qWait(50)
drag(-900,-900);ratio()
assert abs(w.property('visualZoom')-.5)<.001
assert w.width()==round(w.property('baseWidth')*.5)
""")
