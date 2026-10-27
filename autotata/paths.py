from pathlib import Path
import sys

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
ASSETS = Path(getattr(sys, '_MEIPASS', ROOT)) / 'assets'

def settings_path():
    return ROOT / 'settings.json'


def detach_working_directory():
    """Keep long-lived ADB children from pinning the portable install folder."""
    import os
    import tempfile
    os.chdir(tempfile.gettempdir())
