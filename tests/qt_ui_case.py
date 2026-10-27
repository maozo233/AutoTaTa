"""Isolated Qt Quick checks keep the main suite's QCoreApplication untouched."""
import os,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class QtUiCase(unittest.TestCase):
    def run_qt(self,code):
        result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,
            env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software','PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
