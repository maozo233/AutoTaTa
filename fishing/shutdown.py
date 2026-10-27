"""Windows shutdown adapter; call only after an explicitly enabled stop policy."""
import os
import subprocess

def request_shutdown(force=False):
    executable = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'shutdown.exe')
    args = [executable, '/s', '/t', '0']
    if force:
        args.append('/f')
    subprocess.run(args, check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
