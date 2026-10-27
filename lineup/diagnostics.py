"""Portable, local lineup records and an explicitly exported support bundle."""
import hashlib,json,logging,os,platform,shutil,threading,uuid
from datetime import datetime,timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from autotata import __version__
from autotata.paths import ROOT

RETAIN=20
SCHEMA='autotata-lineup-diagnostic-v1'
_lock=threading.RLock()
_active=set()


def now():return datetime.now(timezone.utc).isoformat()


def serial(value):
    if hasattr(value,'item'):return value.item()
    if hasattr(value,'tolist'):return value.tolist()
    if isinstance(value,Path):return str(value)
    raise TypeError(type(value).__name__)


def records(root=ROOT):
    folder=Path(root)/'logs/lineup-runs'
    found=[]
    for path in folder.glob('run-*'):
        if not path.is_dir() or path.is_symlink() or path.is_junction():continue
        try:
            data=json.loads((path/'manifest.json').read_text('utf8'))
            if data.get('schema')==SCHEMA:found.append((path,data))
        except (OSError,ValueError):continue
    return sorted(found,key=lambda item:item[0].name,reverse=True)


def prune(root=ROOT):
    base=(Path(root)/'logs/lineup-runs').resolve()
    with _lock:
        for path,_ in records(root)[RETAIN:]:
            resolved=path.resolve()
            if resolved in _active or resolved.parent!=base or path.is_symlink() or path.is_junction():continue
            try:shutil.rmtree(resolved)
            except OSError:logging.getLogger('lineup').warning('Cannot remove old diagnostic record: %s',resolved,exc_info=True)


class DiagnosticSession:
    def __init__(self,image=None,settings=None,root=ROOT):
        self.root=Path(root);self.lock=threading.RLock();self.closed=False;self.last_hash={}
        stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        self.path=self.root/'logs/lineup-runs'/f'run-{stamp}-{uuid.uuid4().hex[:6]}'
        self.path.mkdir(parents=True)
        self.data={'schema':SCHEMA,'version':__version__,'startedAt':now(),'status':'running',
                   'system':{'platform':platform.platform(),'architecture':platform.machine()},
                   'settings':{k:v for k,v in (settings or {}).items() if k in ('mode','crop_top','crop_bottom')},'stages':{}}
        self.handler=RotatingFileHandler(self.path/'session.log',maxBytes=1_500_000,backupCount=1,encoding='utf8')
        self.handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
        self.handler.setLevel(logging.INFO)
        with _lock:
            _active.add(self.path.resolve());logging.getLogger().addHandler(self.handler)
        try:
            self._manifest()
            if image is not None:self.capture(image,'source')
            prune(self.root)
        except Exception:
            self.finish('failed');raise

    def _manifest(self):
        pending=self.path/'manifest.pending'
        pending.write_text(json.dumps(self.data,ensure_ascii=False,indent=2,default=serial),encoding='utf8')
        os.replace(pending,self.path/'manifest.json')

    def record(self,event,**fields):
        try:
            with self.lock:
                if self.closed:return
                with (self.path/'events.jsonl').open('a',encoding='utf8') as output:
                    output.write(json.dumps({'at':now(),'event':event,**fields},ensure_ascii=False,default=serial)+'\n')
        except Exception:logging.getLogger('lineup').warning('Diagnostic event write failed',exc_info=True)

    def capture(self,frame,slot,**fields):
        # Fixed named slots retain the input, initial field, last action pair,
        # recognition state, failure and final state without recording a video.
        if slot not in ('source','game-initial','game-before-action','game-after-action','game-recognition','game-failure','game-final'):return
        try:
            import cv2
            digest=hashlib.sha256(frame.tobytes()).hexdigest()
            with self.lock:
                if self.closed:return
                if self.last_hash.get(slot)!=digest:
                    ok,pixels=cv2.imencode('.png',frame,[cv2.IMWRITE_PNG_COMPRESSION,1])
                    if not ok:raise OSError('PNG encoding failed')
                    pixels.tofile(self.path/(slot+'.png'));self.last_hash[slot]=digest
                self.record('screenshot',slot=slot,sha256=digest,width=frame.shape[1],height=frame.shape[0],**fields)
        except Exception:logging.getLogger('lineup').warning('Diagnostic screenshot write failed',exc_info=True)

    def stage(self,name,status,**fields):
        try:
            with self.lock:
                if self.closed:return
                self.data['stages'][name]={'status':status,'at':now(),**fields}
                self._manifest();self.record(name,status=status,**fields)
        except Exception:logging.getLogger('lineup').warning('Diagnostic manifest write failed',exc_info=True)

    def finish(self,status=None):
        with self.lock:
            if self.closed:return
            states=[s['status'] for s in self.data['stages'].values()]
            self.data.update(finishedAt=now(),status=status or ('failed' if 'failed' in states else 'partial' if 'partial' in states else 'completed'))
            try:self._manifest()
            except Exception:logging.getLogger('lineup').warning('Diagnostic completion write failed',exc_info=True)
            self.closed=True
            with _lock:
                logging.getLogger().removeHandler(self.handler);self.handler.close();_active.discard(self.path.resolve())
        try:prune(self.root)
        except OSError:logging.getLogger('lineup').warning('Diagnostic retention cleanup failed',exc_info=True)


def export_bundle(destination,root=ROOT):
    """Export owned records and known legacy evidence, never the install tree."""
    root=Path(root);destination=Path(destination)
    if destination.suffix.lower()!='.zip':destination=destination.with_suffix('.zip')
    pending=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.pending')
    entries=[];failures=[]
    try:
        with _lock,ZipFile(pending,'w',ZIP_DEFLATED,compresslevel=6) as archive:
            def add(path,name):
                if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):return
                try:
                    content=path.read_bytes();archive.writestr(name,content)
                    entries.append({'path':name,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()})
                except OSError as exc:failures.append({'path':name,'error':str(exc)})
            sessions=records(root)[:RETAIN]
            allowed={'manifest.json','events.jsonl','session.log','session.log.1',
                     'source.png','game-initial.png','game-before-action.png','game-after-action.png',
                     'game-recognition.png','game-failure.png','game-final.png'}
            for folder,_ in sessions:
                for name in sorted(allowed):add(folder/name,'runs/'+folder.name+'/'+name)
            for relative in ('logs/session.log','logs/session.log.1','maa/debug/maafw.log','lineup-reference.png'):
                add(root/relative,'legacy/'+relative)
            for name in ('last-failed-import','last-uncertain-import'):
                for extension in ('.png','.json'):
                    add(root/'logs/lineup-diagnostics'/(name+extension),'legacy/'+name+extension)
            archive.writestr('bundle.json',json.dumps({'schema':SCHEMA,'version':__version__,'exportedAt':now(),
                'sessions':[{'folder':p.name,'status':d.get('status'),'startedAt':d.get('startedAt')} for p,d in sessions],
                'files':entries,'readErrors':failures},ensure_ascii=False,indent=2))
            archive.writestr('README.txt','AutoTaTa lineup diagnostics\nOpen bundle.json for the record index.\nEach run includes its source formation, session log, events, recognition results and saved game screenshots.\n')
        os.replace(pending,destination)
    finally:
        if pending.exists():pending.unlink()
    return destination
