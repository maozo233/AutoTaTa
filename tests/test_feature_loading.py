"""Use fresh processes: the regression suite itself imports feature modules."""
import os,subprocess,sys,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
class FeatureLoadingTests(unittest.TestCase):
    def check(self,code):
        result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,env={**os.environ,'QT_QPA_PLATFORM':'offscreen'},capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
    def test_home_does_not_load_feature_modules_or_pages(self):
        self.check("""
import sys
from autotata.app import Shell
s=Shell(discover=False,animations=False)
assert not any(n in sys.modules for n in ('fishing','treasure','numpy','cv2','maa'))
assert s.nav.fishing is None and s.nav.treasure is None
assert not s.window.property('treasureLoaded')
assert s.nav.splash is None and s.window.isVisible()
assert not s.errors
""")
    def test_treasure_entry_creates_only_its_backend_and_returns_home(self):
        self.check("""
import sys
from autotata.app import Shell
s=Shell(discover=False,animations=False)
s.nav.openTreasure()
assert s.nav.treasure is not None and s.nav.fishing is None
assert 'fishing.engine' not in sys.modules and 'fishing.gpu_app' not in sys.modules
assert s.window.property('page')=='treasure' and s.window.property('treasureLoaded')
s.nav.returnHome()
assert s.window.property('page')=='home'
assert not s.errors
s.treasure.close()
""")
    def test_lineup_entry_opens_without_starting_automation(self):
        self.check("""
from PySide6.QtCore import QObject
from autotata.app import Shell
s=Shell(discover=False,animations=False)
def find_visual(item,name):
    if item.objectName()==name:return item
    for child in item.childItems():
        found=find_visual(child,name)
        if found is not None:return found
entry=find_visual(s.window.contentItem(),'entry0')
entry.clicked.emit()
s.application.processEvents()
assert s.window.property('page')=='lineup'
assert s.nav.lineup is not None and not s.nav.lineup.state['running']
assert all(getattr(s.nav,n) is None for n in ('fishing','treasure','rafting'))
assert not s.errors
s.nav.lineup.close()
""")

if __name__=='__main__':unittest.main()
