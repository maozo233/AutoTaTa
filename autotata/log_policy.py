"""Bound diagnostic text logs; retain recent records, never frames or settings."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import threading
from dataclasses import dataclass
from .paths import ROOT

MAX_LOG_BYTES=5_000_000
SESSION_BYTES=1_500_000
NATIVE_BYTES=1_500_000
# Normal retained total is 4.5 MB, leaving 0.5 MB for native writes between sweeps.
native_log_lock=threading.RLock()
_removed={}
_service=None

@dataclass(frozen=True)
class LogCursor:
    position:int


def trim_tail(path,limit):
    path=Path(path)
    with native_log_lock:
        try:
            with path.open('r+b') as stream:
                size=stream.seek(0,2)
                if size<=limit:return 0
                stream.seek(max(0,size-limit))
                tail=stream.read()
                # Start on a complete record, or a UTF-8 boundary for a huge line.
                newline=tail.find(b'\n')
                if newline>=0 and newline<len(tail)-1:tail=tail[newline+1:]
                else:tail=tail.decode('utf-8',errors='ignore').encode('utf-8')
                stream.seek(0);stream.write(tail);stream.truncate();stream.flush()
                removed=size-len(tail)
                _removed[str(path.resolve())]=_removed.get(str(path.resolve()),0)+removed
                return removed
        except (OSError,ValueError):return 0


def log_cursor(path):
    with native_log_lock:
        try:return LogCursor(Path(path).stat().st_size+_removed.get(str(Path(path).resolve()),0))
        except OSError:return LogCursor(0)


def cursor_offset(path,cursor):
    if not isinstance(cursor,LogCursor):return cursor
    return max(0,cursor.position-_removed.get(str(Path(path).resolve()),0))


class BoundedSessionHandler(RotatingFileHandler):
    def __init__(self,path,max_bytes=SESSION_BYTES):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        trim_tail(path,max_bytes)
        trim_tail(str(path)+'.1',max_bytes)
        super().__init__(path,maxBytes=max_bytes,backupCount=1,encoding='utf-8',delay=True)
    def _open(self):return open(self.baseFilename,self.mode,encoding='utf-8',newline='')
    def handle(self,record):
        # Always take the shared lock before Handler.lock to avoid inversion
        # with input diagnosis, which also logs while holding this lock.
        with native_log_lock:return super().handle(record)
    def emit(self,record):
        try:
            data=(self.format(record)+'\n').encode('utf-8')
            if len(data)>min(65536,self.maxBytes):
                limit=min(65536,self.maxBytes)
                data=b'[truncated] '+data[-max(0,limit-12):].decode('utf-8',errors='ignore').encode('utf-8')
            if self.stream is None:self.stream=self._open()
            self.stream.seek(0,2)
            if self.stream.tell()+len(data)>self.maxBytes:
                try:self.doRollover()
                except OSError:
                    # An older running copy may hold the file against renaming.
                    if self.stream:self.stream.close();self.stream=None
                    trim_tail(self.baseFilename,max(0,self.maxBytes-len(data)))
                if self.stream is None:self.stream=self._open()
            self.stream.write(data.decode('utf-8'));self.flush()
        except Exception:self.handleError(record)


class LogMaintenance:
    def __init__(self,root):
        self.root=Path(root);self.stop_event=threading.Event();self.thread=None
    def sweep(self):
        with native_log_lock:
            session=self.root/'logs/session.log'
            # Old backups from former policies must not accumulate.
            for path in session.parent.glob('session.log.*'):
                if path.name!='session.log.1':
                    try:path.unlink()
                    except OSError:pass
            trim_tail(session,SESSION_BYTES);trim_tail(str(session)+'.1',SESSION_BYTES)
            current=[]
            for folder in (self.root/'maa/debug',self.root/'build/maa/debug'):
                for path in folder.glob('*.log'):
                    if path.name=='maafw.log':current.append(path)
                    else:
                        try:path.unlink()
                        except OSError:pass
            if current:
                share=NATIVE_BYTES//len(current)
                for path in current:trim_tail(path,share)
    def start(self):
        self.sweep()
        if self.thread:return
        def loop():
            while not self.stop_event.wait(.5):self.sweep()
        self.thread=threading.Thread(target=loop,name='LogMaintenance',daemon=True);self.thread.start()
    def close(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=2)
        self.sweep()


def start_maintenance(root=ROOT):
    global _service
    if _service is None:
        _service=LogMaintenance(root);_service.start()
    return _service


def configure_logging(root=ROOT):
    root=Path(root)
    handler=BoundedSessionHandler(root/'logs/session.log')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logging.basicConfig(level=logging.INFO,handlers=[handler],force=True)
    return start_maintenance(root)
