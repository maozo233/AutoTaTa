"""MuMu SDK read-only session. No click controller is constructed."""
import subprocess,threading,time,logging
from PySide6.QtCore import QObject,Signal
from .vision import observe,read_stage,read_cost

def disappearance_groups(size,indices):
    """Connected cells vanishing together; diagonals do not join treasures."""
    left=set(indices);groups=[]
    while left:
        group={left.pop()};stack=list(group)
        while stack:
            i=stack.pop();r,c=divmod(i,size)
            for dr,dc in ((1,0),(-1,0),(0,1),(0,-1)):
                rr,cc=r+dr,c+dc;j=rr*size+cc
                if 0<=rr<size and 0<=cc<size and j in left:left.remove(j);group.add(j);stack.append(j)
        groups.append(group)
    return groups

class ObservationConfirmation:
    """Confirm transient foreground and completion colors without blocking capture."""
    def __init__(self,delay=2.3):
        self.delay=delay;self.size=None;self.pending={};self.cells=[];self.completed={};self.raw_cells=[];self.completed_events=set();self.transient_events=set()
    def reset(self):
        self.size=None;self.pending={};self.cells=[];self.completed={};self.raw_cells=[];self.completed_events=set();self.transient_events=set()
    def acknowledge(self):
        self.completed_events.clear();self.transient_events.clear()
    def apply(self,observation,now):
        from dataclasses import replace
        if self.size!=observation.size:
            self.reset();self.size=observation.size;self.cells=[0]*len(observation.cells)
        cells=observation.cells[:];foreground=observation.foreground.copy();pending=[]
        vanished={i for i,(old,new) in enumerate(zip(self.raw_cells,observation.cells)) if old==2 and new==1}
        for group in disappearance_groups(self.size,vanished):
            if len(group)>=2 and any(self.cells[i]==2 for i in group):
                self.completed_events.update(group);self.transient_events.difference_update(group)
            else:self.transient_events.update(group)
        self.raw_cells=observation.cells[:]
        for i,value in enumerate(cells):
            if value==2 and self.cells[i]!=2:
                since=self.pending.setdefault(i,now)
                if now-since<self.delay:
                    cells[i]=-1;pending.append(i)
                    r,c=divmod(i,self.size);foreground[r*32:(r+1)*32,c*32:(c+1)*32]=0
                else:self.cells[i]=2;self.pending.pop(i,None)
            elif value!=2:
                self.pending.pop(i,None);self.cells[i]=value
        items=[]
        for item in observation.silhouettes:
            item=dict(item);a,b,w,h=item['box']
            key=(round((a+w/2)/observation.tray[2]*20),round((b+h/2)/observation.tray[3]*20)) if observation.tray else item['box']
            if item.get('completed'):
                since=self.completed.setdefault(key,now)
                item['completed']=now-since>=self.delay
            else:self.completed.pop(key,None)
            items.append(item)
        return replace(observation,cells=cells,foreground=foreground,silhouettes=items,pending_cells=tuple(pending),completed_cells=tuple(sorted(self.completed_events)),transient_cells=tuple(sorted(self.transient_events)))

class Watcher(QObject):
    observed=Signal(int,object,object,object)
    status=Signal(int,str)
    stopped=Signal(int)
    boardSeen=Signal(int)
    boardChanged=Signal(int)
    def __init__(self,hwnd,generation):
        super().__init__();self.hwnd=hwnd;self.generation=generation;self.cancel=threading.Event();self.thread=None
    def start(self):
        self.thread=threading.Thread(target=self.run,daemon=True,name='Treasure capture');self.thread.start()
    def stop(self):self.cancel.set()
    def run(self):
        probe=None
        try:
            from fishing.adb_session import discover_mumu_device
            from fishing.display_probe import DisplayProbe,parse_displays
            from fishing.windows import process_id,process_name
            device=discover_mumu_device(self.hwnd);pid=process_id(self.hwnd)
            subprocess.run([str(device.adb_path),'connect',device.address],capture_output=True,timeout=8,creationflags=subprocess.CREATE_NO_WINDOW,check=True)
            result=subprocess.run([str(device.adb_path),'-s',device.address,'shell','dumpsys window displays'],capture_output=True,timeout=8,creationflags=subprocess.CREATE_NO_WINDOW,check=True)
            displays=parse_displays(result.stdout.decode('utf8',errors='replace'))
            if not displays:raise RuntimeError('无法枚举 MuMu 显示区')
            probe=DisplayProbe(device)
            confirmation=ObservationConfirmation()
            hints={};selected=None;ocr=None;last_ocr=0;stage=None;cost=None;previous=None;stable=0;missing=0;accepted=None;new_session=False;seen_board=False
            while not self.cancel.is_set():
                if process_id(self.hwnd)!=pid or process_name(pid).lower()!='mumunxdevice.exe':raise RuntimeError('目标 MuMu 已退出')
                matches=[]
                for display in ([selected] if selected is not None else sorted(displays)):
                    frame=probe.read(display)
                    if frame is not None:
                        observation=observe(frame,hints.get(display))
                        if observation:
                            hints[display]=observation;matches.append((display,frame,observation))
                if len(matches)!=1:
                    missing+=1;previous=None;stable=0
                    self.status.emit(self.generation,'未找到稳定棋盘，请进入营地寻宝')
                    if missing>=3 and seen_board:new_session=True;last_ocr=0;confirmation.reset()
                    if missing>=6:selected=None
                    self.cancel.wait(.5);continue
                missing=0;selected,frame,observation=matches[0]
                if previous is not None and any(v in (1,2,-1) for v in previous[1]) and all(v==0 for v in observation.cells):confirmation.reset()
                observation=confirmation.apply(observation,time.monotonic())
                self.boardSeen.emit(self.generation)
                key=(observation.size,tuple(observation.cells),tuple(item.get('completed',False) for item in observation.silhouettes))
                if previous is not None and any(v in (1,2) for v in previous[1]) and all(v==0 for v in key[1]):last_ocr=0
                stable=stable+1 if key==previous else 0;previous=key
                if accepted is not None and key!=accepted:
                    self.boardChanged.emit(self.generation);accepted=None
                if stable>=2:
                    accepted=key
                    if time.monotonic()-last_ocr>4:
                        if ocr is None:
                            from rapidocr_onnxruntime import RapidOCR
                            ocr=RapidOCR(intra_op_num_threads=1,inter_op_num_threads=1)
                        stage=read_stage(frame,observation.tray,ocr);cost=read_cost(frame,observation.rect,ocr);last_ocr=time.monotonic()
                    self.observed.emit(self.generation,frame,observation,{'stage':stage,'cost':cost,'newSession':new_session})
                    confirmation.acknowledge()
                    new_session=False;seen_board=True
                self.cancel.wait(.45)
        except Exception as exc:
            logging.getLogger('treasure').exception('Capture stopped')
            self.status.emit(self.generation,'识别停止：'+str(exc))
        finally:
            if probe:probe.close()
            self.stopped.emit(self.generation)
