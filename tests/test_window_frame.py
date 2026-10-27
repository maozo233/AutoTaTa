from tests.qt_ui_case import QtUiCase

class NativeFrameCompatibilityTests(QtUiCase):
    def test_all_feature_windows_remain_opaque_and_headless_compatible(self):
        self.run_qt('''
from autotata.app import Shell
from PySide6.QtTest import QTest
s=Shell(discover=False,animations=False)
assert not s.window_frame.enabled
for page,open_page in [('home',lambda:None),('rafting',s.nav.openRafting),('treasure',s.nav.openTreasure)]:
    open_page();QTest.qWait(30)
    assert s.window.property('page')==page
    assert s.window.color().alpha()==255
    assert abs(s.window.width()-s.window.property('baseWidth')*s.window.property('visualZoom'))<=1
    assert not s.window_frame.snapshot()['errors']
s.nav.openFishing()
f=s.nav.fishing
assert f.window.color().alpha()==255 and not f.window_frame.enabled
assert not s.errors and not f.qml_errors
f.backend.timer.stop();s.treasure.close()
''')
