"""One persistent standard-ADB screenshot process; latest frames remain in RAM."""
import subprocess,threading,queue,base64,time
import cv2,numpy as np

class AdbFrameStream:
    def __init__(self,adb,address,remote,cancel):
        self.cancel=cancel;self.frames=queue.Queue(maxsize=2);self.errors=[]
        self.process=subprocess.Popen([adb,'-s',address,'shell','-T',f'env CLASSPATH={remote} app_process /data/local/tmp com.tata.autofish.Snapshot stream'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        threading.Thread(target=self._reader,daemon=True).start()
        threading.Thread(target=self._stderr,daemon=True).start()
    def _stderr(self):
        try:
            for line in iter(self.process.stderr.readline,b''):
                self.errors.append(line.decode('utf-8',errors='replace')[:300]);self.errors=self.errors[-8:]
        except (OSError,ValueError):pass
    def _reader(self):
        try:
            while True:
                line=self.process.stdout.readline(64*1024*1024)
                if not line:raise EOFError('ADB screenshot stream ended')
                if len(line)>=64*1024*1024 or line.strip()==b'ERROR':raise RuntimeError('ADB screenshot unavailable')
                data=base64.b64decode(line.strip(),validate=True)
                frame=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
                if frame is None:raise RuntimeError('ADB screenshot decoding failed')
                self.frames.put((frame,time.monotonic()))
        except Exception as exc:
            try:self.frames.put_nowait(exc)
            except queue.Full:pass
    def read(self,display):
        if self.cancel.is_set():raise RuntimeError('已收到停止指令。')
        try:
            self.process.stdin.write(f'{int(display)}\n'.encode());self.process.stdin.flush()
        except (OSError,ValueError) as exc:raise RuntimeError('ADB 截图长连接已断开。') from exc
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            if self.cancel.is_set():raise RuntimeError('已收到停止指令。')
            try:item=self.frames.get(timeout=.05)
            except queue.Empty:continue
            if isinstance(item,Exception):raise RuntimeError('ADB 截图失败；未继续点击。'+''.join(self.errors)[-250:]) from item
            return item
        raise RuntimeError('ADB 截图超时，已停止。')
    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        for stream in (self.process.stdin,self.process.stdout,self.process.stderr):
            try:stream.close()
            except OSError:pass
