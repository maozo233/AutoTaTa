# Reproducible single-file release with explicit runtime-only contents.
from pathlib import Path
import subprocess, json, sys
from PyInstaller.utils.hooks import collect_all
root=Path(SPECPATH).parent
subprocess.run([sys.executable, str(root/'tools/check_ui_fonts.py')], check=True)
datas=[(str(root/'assets'),'assets'),(str(root/'licenses'),'licenses')]
binaries=[];hiddenimports=[]
for package in ('maa','MaaAgentBinary','windows_capture','rapidocr_onnxruntime','onnxruntime'):
    data,libs,imports=collect_all(package)
    datas+=data;binaries+=libs;hiddenimports+=imports
analysis=Analysis([str(root/'main.py')],pathex=[str(root)],binaries=binaries,datas=datas,
                  hiddenimports=hiddenimports,excludes=['PIL.AvifImagePlugin','PIL._avif','tkinter'])
# Keep only QML modules used by this UI, including their recursive dependencies.
qt_root=Path(sys.prefix)/'Lib/site-packages/PySide6'
imports=json.loads(subprocess.check_output([str(qt_root/'qmlimportscanner.exe'),
    '-rootPath',str(root/'assets/ui'),'-importPath',str(qt_root/'qml')],text=True))
qml_modules={item['relativePath'].lower() for item in imports if 'relativePath' in item}
qml_modules.add('qtquick/controls')
(root/'validation/qml-imports.json').write_text(json.dumps(sorted(qml_modules),indent=2),encoding='utf-8')
def runtime_file(entry):
    name=entry[0].replace('\\','/').lower()
    # Qt on Windows uses the OS ICU API. The workspace's Poppler ICU has
    # incompatible version-suffixed exports and must not shadow that DLL.
    if name in ('icuuc.dll','icuin.dll','icudt78.dll'):return False
    if name.startswith('assets/fixtures/'):return False
    if name.startswith('assets/lineup/'):
        return name.startswith(('assets/lineup/tatari/','assets/lineup/filters/')) or name in ('assets/lineup/catalog.json','assets/lineup/clear-five.png','assets/lineup/clear-fifteen.png')
    if name.startswith('cv2/') and ('opencv_videoio_ffmpeg' in name or '/haarcascade' in name):return False
    if name.startswith('pyside6/qml/'):
        relative=name[len('pyside6/qml/'):]
        parent=relative.rsplit('/',1)[0] if '/' in relative else ''
        return parent in qml_modules
    return True
analysis.binaries=[entry for entry in analysis.binaries if runtime_file(entry)]
analysis.datas=[entry for entry in analysis.datas if runtime_file(entry)]
pyz=PYZ(analysis.pure)
exe=EXE(pyz,analysis.scripts,analysis.binaries,analysis.datas,[],name='AutoTaTa',
        debug=False,strip=False,upx=False,console=False,icon=str(root/'assets/app.ico'),runtime_tmpdir=None)
