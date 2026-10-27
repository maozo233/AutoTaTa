"""Bind upstream MaaTouch to the same MuMu display as EmulatorExtras capture."""
import copy
import hashlib
import subprocess
from .paths import ASSETS

def prepare_maatouch_display(device, binding=None):
    if binding is None:
        from .display_probe import inspect_fishing_displays
        config,binding=inspect_fishing_displays(device)
    else:
        config=copy.deepcopy(device.config)
    config=copy.deepcopy(config)
    display,width,height=binding
    asset=ASSETS/'maatouch-display.dex'
    if not asset.is_file():raise RuntimeError('缺少 MaaTouch 显示区补丁，请重新解压完整程序。')
    digest=hashlib.sha256(asset.read_bytes()).hexdigest()[:16]
    remote=f'/data/local/tmp/tata-maatouch-{digest}.dex'
    result=subprocess.run([str(device.adb_path),'-s',device.address,'push',str(asset),remote],
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=8,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise RuntimeError('MaaTouch 显示区补丁传输失败。')
    # The patched agent accepts the target display's visible coordinates directly.
    # Do not rotate using dumpsys input's unrelated default-display orientation.
    commands=config.setdefault('command',{})
    shell=['{ADB}','-s','{ADB_SERIAL}','shell']
    commands['Resolution']=shell+[f'echo {width} {height} 0']
    commands['Orientation']=shell+['echo 0']
    commands['InvokeApp']=shell+[f'export CLASSPATH="{remote}:/data/local/tmp/{{APP_WORKING_FILE}}"; app_process /data/local/tmp {{PACKAGE_NAME}} {display}']
    return config,(display,width,height)
