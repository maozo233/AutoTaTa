from tests.qt_ui_case import QtUiCase
SETUP="""
from pathlib import Path
from PySide6.QtCore import QUrl,QCoreApplication,QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine,QQmlComponent
from PySide6.QtTest import QTest,QSignalSpy
app=QGuiApplication([]);engine=QQmlEngine();errors=[]
engine.warnings.connect(lambda es:errors.extend(e.toString() for e in es))
component=QQmlComponent(engine,QUrl.fromLocalFile(str(Path('assets/ui/ActionButton.qml').resolve())))
button=component.create();assert button is not None,component.errors()
QTest.qWait(20)
"""
class MotionTests(QtUiCase):
    def test_retarget_preserves_current_position_and_finishes(self):
        self.run_qt(SETUP+"""
button.setProperty('down',True);QTest.qWait(50)
current=button.property('scale');assert .975<current<1,current
button.setProperty('down',False)
assert abs(button.property('scale')-current)<.002
QTest.qWait(250);assert abs(button.property('scale')-1)<.0001
assert not errors,errors
""")
    def test_destroy_cancels_animation_safely(self):
        self.run_qt(SETUP+"""
button.setProperty('down',True);QTest.qWait(35)
spy=QSignalSpy(button.destroyed)
button.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
QTest.qWait(200);assert spy.count()==1
assert not errors,errors
""")
    def test_stationary_target_has_no_animation_changes(self):
        self.run_qt(SETUP+"""
spy=QSignalSpy(button.scaleChanged)
button.setProperty('down',False);QTest.qWait(200)
assert spy.count()==0 and button.property('scale')==1
assert not errors,errors
""")
