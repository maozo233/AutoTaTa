import copy,json,threading
from PySide6.QtCore import QObject,Property,Signal,Slot,QTimer
from autotata.paths import ASSETS
from .solver import solve,estimate,estimate_guided

class TreasureBackend(QObject):
    changed=Signal()
    computed=Signal(int,object)
    imported=Signal(object,object,object,str)
    def __init__(self,discover=True):
        super().__init__()
        self.presets=json.loads((ASSETS/'treasure/presets.json').read_text(encoding='utf-8'))['stages']
        self.closing=False;self.solver_thread=None;self.dismissed_predictions=set();self.history=[];self.revision=0;self.masks=[];self.busy=False;self.pending_calculation=False
        self._state={};self.computed.connect(self.finish)
        self.live={'devices':[],'deviceIndex':0,'running':False,'overlay':True,'status':'进入寻宝棋盘后开始识别','autoConfig':True,'ghosts':0}
        self.watcher=None;self.generation=0;self.observation=None;self.templates=[];self.pins={};self.overrides={};self.board_key=None;self.last_key=None
        self.retry_timer=QTimer(self);self.retry_timer.setSingleShot(True);self.retry_timer.setInterval(2000);self.retry_timer.timeout.connect(self.startWatch)
        self.transition_candidate=None;self.transition_count=0
        self.overlay_window=None;self.snapshot_ready=False;self.imageBusy=False;self.imported.connect(self.finishImport)
        self.selectStage(1,internal=True)
        if discover:self.refreshDevices()
    @Property('QVariantMap',notify=changed)
    def state(self):
        from .presentation import recognition_status
        warning=self.live.get('configurationWarning','')
        confirmed={tuple(sorted((w,h))):count for w,h,count in self._state.get('confirmedShapes',[])}
        totals={}
        for w,h,count in self._state['shapes']:
            key=tuple(sorted((w,h)));totals[key]=totals.get(key,0)+count
        treasures_confirmed=bool(confirmed) and all(count<=confirmed.get(key,0) for key,count in totals.items())
        if treasures_confirmed and any(word in warning for word in ('估算','不完整')):warning=''
        board_warning=self.live.get('boardWarning','')
        unknown=self.live.get('unknownCells',[])
        unresolved=[i for i in unknown if i not in self.overrides]
        if unresolved:board_warning=f'{len(unresolved)} 个格子未识别，请点击格子校正'
        if any(word in self._state.get('status','') for word in ('计算失败','没有符合标记','暂未采到','配置无效')):
            warning='宝物或格子标记不匹配，请核对尺寸、数量及标记'
            board_warning='格子标记与宝物配置不匹配，请核对'
        return copy.deepcopy({**self._state,'live':self.live,'configurationWarning':warning,'boardWarning':board_warning,'dismissedPredictions':sorted(self.dismissed_predictions),
            'treasuresConfirmed':treasures_confirmed,'recognitionStatus':recognition_status(self.live,self.snapshot_ready,board_warning or warning)})
    def checkpoint(self):self.history.append((copy.deepcopy(self._state),dict(self.overrides),copy.deepcopy(self.pins),self.templates,self.observation,self.live['autoConfig'],set(self.dismissed_predictions)));self.history=self.history[-100:]
    @Slot(int)
    def selectStage(self,stage,internal=False):
        if not 1<=stage<=24:return
        if self._state:self.checkpoint()
        self.dismissed_predictions=set()
        self.live.update(configurationWarning='',boardWarning='',unknownCells=[],derived=False)
        if not internal:self.live['autoConfig']=False
        self.overrides={};self.pins={};self.templates=[];self.observation=None;self.last_key=None;self.completed_count=0
        p=copy.deepcopy(self.presets[stage-1])
        self._state={**p,'cells':[0]*(p['size']**2),'probabilities':[],'status':'请按实际挖掘结果标记棋盘','estimate':'尚未估算','busy':False,'canUndo':bool(self.history),'templateCount':0,'templatesPreview':[],'pinStatus':'尚未手动定位','treasureHistory':[],'completedTreasure':[],'completedSlots':[],'trayShapes':[],'completedCount':0,'completedGroups':[],'unresolvedGround':[]}
        self.invalidate()
    def invalidate(self):
        if self.overlay_window:
            existing=self.overlay_window.data
            same_board=isinstance(existing,dict) and self.observation is not None and existing.get('size')==self._state['size'] and tuple(existing.get('rect',()))==tuple(self.observation.rect)
            if not same_board:
                self.overlay_window.publish({'size':self._state['size'],'cells':self._state['cells'][:],
                    'probabilities':[],'completedTreasure':self._state.get('completedTreasure',[]),'rect':self.observation.rect} if self.observation else {})
        # Keep the last inferred scope while the replacement calculation is pending.
        inferred=set(self._state.get('predictedTreasure',[]))|set(self._state.get('candidateTreasure',[]))|set(self._state.get('certainTreasure',[]))
        if inferred:self._state['completionScope']=sorted(inferred)
        self.revision+=1;self.masks=[]
        self._state.update(allIdentified=False,pendingShapes=self._state['shapes'],probabilities=[],certainTreasure=[],candidateTreasure=[],predictedTreasure=[],markedTreasure=self._state.get('completedTreasure',[])[:],recommendedCells=[],ghostItems=[],estimate='等待读取棋盘',estimatePrimary='等待读取棋盘',estimateDetails='',busy=self.busy,canUndo=bool(self.history),status='棋盘已更新，请重新计算')
        self.changed.emit()
    @Slot(int,int)
    def mark(self,index,value):
        if 0<=index<len(self._state['cells']) and value in (0,1,2):
            self.checkpoint()
            if value==0 and index in self._state.get('predictedTreasure',[])+self._state.get('candidateTreasure',[]):self.dismissed_predictions.add(index)
            elif value!=0:self.dismissed_predictions.discard(index)
            self._state['allLocated']=False
            if value==2:self._state['treasureHistory']=sorted(set(self._state.get('treasureHistory',[]))|{index})
            if value!=2:
                self._state['completionScope']=[i for i in self._state.get('completionScope',[]) if i!=index]
                for field in ('treasureHistory','completedTreasure'):self._state[field]=[i for i in self._state.get(field,[]) if i!=index]
            self.overrides[index]=value;self._state['cells'][index]=value;self.invalidate()
            self.calculate()
    @Slot()
    def undo(self):
        if self.history:
            self._state,self.overrides,self.pins,self.templates,self.observation,self.live['autoConfig'],self.dismissed_predictions=self.history.pop();self.completed_count=self._state.get('completedCount',0);self.live['completedTreasures']=self.completed_count;self.last_key=None;self.invalidate();self.calculate()
    @Slot()
    def clear(self):
        self.checkpoint()
        self._state['allLocated']=False
        self._state.update(treasureHistory=[],completedTreasure=[],completionScope=[]);self.overrides={i:0 for i in range(len(self._state['cells']))};self._state['cells']=[0]*len(self._state['cells']);self.invalidate();self.calculate()
    @Slot(int,int,str,result=bool)
    def configure(self,size,cost,description):
        try:
            if not 3<=size<=9 or not 1<=cost<=9999:raise ValueError()
            shapes=[]
            for part in filter(None,description.replace('×','x').replace('，',',').split(',')):
                dimensions,count=part.strip().split(':');w,h=map(int,dimensions.split('x'));count=int(count)
                if not 1<=w<=size or not 1<=h<=size or not 1<=count<=20:raise ValueError()
                shapes.append([w,h,count])
            if sum(w*h*c for w,h,c in shapes)>size*size:raise ValueError()
        except (ValueError,TypeError):
            self._state['status']='配置无效：尺寸、数量或总占格超过棋盘限制';self.changed.emit();return False
        self.checkpoint()
        self._state['allLocated']=False;self._state['confirmedShapes']=[]
        self.live.update(autoConfig=False,configurationWarning='',boardWarning='',unknownCells=[],derived=False);self._state['unresolvedGround']=[];self._state['completionScope']=[];self.templates=[];self.pins={};self.last_key=None
        self._state.update(templateCount=0,templatesPreview=[],pinStatus='尚未手动定位',predictedTreasure=[],candidateTreasure=[],certainTreasure=[],markedTreasure=[])
        if size!=self._state['size']:
            self._state.update(cells=[0]*(size*size),treasureHistory=[],completedTreasure=[],completedSlots=[],trayShapes=[],completedGroups=[],unresolvedGround=[]);self.overrides={}
        self._state.update(stage=0,size=size,cost=cost,shapes=shapes,status='已应用自定义配置');self.invalidate()
        return True
    @Slot(int,int,int,int,result=bool)
    def editTreasure(self,index,width,height,count):
        shapes=copy.deepcopy(self._state['shapes'])
        if not -1<=index<len(shapes) or not 1<=width<=self._state['size'] or not 1<=height<=self._state['size'] or not 0<=count<=20:
            self._state['status']='请检查宝物尺寸和数量';self.changed.emit();return False
        if index==-1:
            if count==0:return False
            shapes.append([width,height,count])
        elif count==0:shapes.pop(index)
        else:shapes[index]=[width,height,count]
        ok=self.configure(self._state['size'],self._state['cost'],','.join(f'{w}x{h}:{c}' for w,h,c in shapes))
        if ok:self.calculate()
        return ok

    @Slot(result=bool)
    def confirmTreasures(self):
        shapes=self._state['shapes'];size=self._state['size']
        if not shapes or any(not (1<=w<=size and 1<=h<=size and 1<=count<=20) for w,h,count in shapes) or sum(w*h*count for w,h,count in shapes)>size*size:
            self.live['configurationWarning']='宝物配置无效，请修改尺寸与数量';self.changed.emit();return False
        # Acknowledge this board's configuration without stopping live capture or completion tracking.
        from collections import Counter
        confirmed=Counter()
        for w,h,count in shapes:confirmed[tuple(sorted((w,h)))]+=count
        self._state['confirmedShapes']=[[w,h,count] for (w,h),count in sorted(confirmed.items())]
        self.changed.emit();return True

    @Slot(int,int,result=bool)
    def changeQuantity(self,index,delta):
        if not 0<=index<len(self._state['shapes']):return False
        w,h,count=self._state['shapes'][index]
        return self.editTreasure(index,w,h,count+delta)

    @Slot(int,int,result=bool)
    def editBoard(self,size,cost):
        if size==self._state['size'] and cost==self._state['cost']:return True
        ok=self.configure(size,cost,','.join(f'{w}x{h}:{c}' for w,h,c in self._state['shapes']))
        if ok:self.calculate()
        return ok

    @Slot()
    def calculate(self):
        if self.closing:return
        if self.busy:
            self.pending_calculation=True;return
        self.pending_calculation=False
        if self._state.get('unresolvedGround'):
            self._state.update(probabilities=[None]*len(self._state['cells']),recommendedCells=[],status='宝物共同消失，等待托盘确认',estimatePrimary='等待宝物完成确认',estimateDetails='')
            self.live['status']='宝物共同消失，等待托盘确认'
            if self.overlay_window:self.overlay_window.publish({'size':self._state['size'],'cells':self._state['cells'][:],'probabilities':self._state['probabilities'],'completedTreasure':self._state.get('completedTreasure',[]),'rect':self.observation.rect if self.observation else ()})
            self.changed.emit();return
        if self._state.get('allLocated'):
            located=self._state.get('locatedCells',[])
            hits={i for i,v in enumerate(self._state['cells']) if v==2}
            if all(self._state['cells'][i]!=1 for i in located) and hits.issubset(located) and len(located)==sum(w*h*c for w,h,c in self._state['shapes']):
                self.showLocated(located);self.changed.emit();return
            self._state.update(allLocated=False,pendingShapes=self._state['shapes'])
        snapshot=self.state;revision=self.revision;self.busy=True
        templates=copy.deepcopy(self.templates);observation=self.observation;pins=copy.deepcopy(self.pins)
        self._state.update(busy=True,status='正在计算可行布局…');self.changed.emit()
        def work():
            try:
                result=None
                if templates and observation is not None:
                    from .inference import infer
                    result=infer(snapshot['size'],templates,snapshot['cells'],observation.foreground,pins=pins,stop_when_identified=True)
                if result is None and pins:raise ValueError('未找到符合手动定位的布局，请检查或清除定位')
                if result is None:result=solve(snapshot['size'],snapshot['shapes'],snapshot['cells'])
                from .presentation import located_progress,markers_and_recommendations,trusted_ghosts
                if 'certainCells' not in result:
                    result['certainCells']=[i for i in range(len(snapshot['cells'])) if result.get('exact') and result['masks'] and all(mask & (1<<i) for mask in result['masks'])]
                result['certainCells']=[i for i in result['certainCells'] if i not in snapshot['dismissedPredictions']]
                result['ghosts']=trusted_ghosts(result.get('ghosts',[]),snapshot['dismissedPredictions'],snapshot['size'])
                inferred=[(g['y']+dy)*snapshot['size']+g['x']+dx for g in result.get('ghosts',[]) for dy in range(g['h']) for dx in range(g['w'])]
                marked,_=markers_and_recommendations(snapshot['cells'],result['probabilities'],result.get('certainCells',[]),inferred)
                progress=located_progress(snapshot['size'],snapshot['shapes'],snapshot['cells'],marked)
                result['locationProgress']=progress
                from .presentation import pending_identified
                identities_found='identifiedShapes' in result and not pending_identified(snapshot['shapes'],result['identifiedShapes'])
                if (progress['complete'] or identities_found) and result['masks']:
                    result['estimate']=None;result['guided']=None
                    if not self.closing:self.computed.emit(revision,result)
                    return
                result['estimate']=estimate(result['masks'],snapshot['cells'],snapshot['cost'])
                from .presentation import markers_and_recommendations
                inferred=[(g['y']+dy)*snapshot['size']+g['x']+dx for g in result.get('ghosts',[]) for dy in range(g['h']) for dx in range(g['w'])]
                from .presentation import candidate_ghosts
                tentative=[(g['y']+dy)*snapshot['size']+g['x']+dx for g in candidate_ghosts(result.get('candidateGhosts',[]),snapshot['dismissedPredictions'],snapshot['size']) for dy in range(g['h']) for dx in range(g['w'])]
                deferred,_=markers_and_recommendations(snapshot['cells'],result['probabilities'],result.get('certainCells',[]),inferred+tentative,tentative)
                from .presentation import pending_identified
                if 'identifiedShapes' in result and not pending_identified(snapshot['shapes'],result['identifiedShapes']):deferred=[]
                result['guided']=estimate_guided(result['masks'],snapshot['cells'],snapshot['cost'],deferred=deferred)
            except Exception as exc:result={'error':str(exc)}
            if not self.closing:self.computed.emit(revision,result)
        self.solver_thread=threading.Thread(target=work,daemon=True);self.solver_thread.start()
    @Slot(int,object)
    def finish(self,revision,result):
        if self.closing:return
        self.busy=False
        if revision!=self.revision:
            self._state['busy']=False;self.changed.emit()
            if self.live['running'] or self.pending_calculation:self.calculate()
            return
        self._state['busy']=False
        if 'error' in result:self._state['status']='计算失败：'+result['error']
        else:
            self.masks=result['masks'];self._state['probabilities']=result['probabilities']
            # Certainty is structural across all exact layouts, never a rounded probability.
            certain=result.get('certainCells')
            if certain is None:
                certain=[i for i in range(len(self._state['cells'])) if result['exact'] and self.masks and all(m & (1<<i) for m in self.masks)]
            certain=[i for i in certain if i not in self.dismissed_predictions]
            self._state['certainTreasure']=certain
            count=len(self.masks)
            self._state['status']=(f'精确计算 · {count} 种布局' if result['exact'] else f'抽样估计 · {count} 个有效样本') if count else ('没有符合标记的布局，请检查或撤销' if result['exact'] else '暂未采到可行布局，请补充信息后重算')
            from .presentation import trusted_ghosts,candidate_ghosts
            candidates=candidate_ghosts(result.get("candidateGhosts",[]),self.dismissed_predictions,self._state["size"])
            self._state["candidateTreasure"]=sorted({(g["y"]+dy)*self._state["size"]+g["x"]+dx for g in candidates for dy in range(g["h"]) for dx in range(g["w"])})
            ghosts=trusted_ghosts(result.get('ghosts',[]),self.dismissed_predictions,self._state['size']);self.live['ghosts']=len(ghosts)
            strong_predicted=sorted({(g['y']+dy)*self._state['size']+g['x']+dx for g in ghosts for dy in range(g['h']) for dx in range(g['w']) if 0<=g['x']+dx<self._state['size'] and 0<=g['y']+dy<self._state['size']})
            self._state['predictedTreasure']=sorted(set(strong_predicted)|set(self._state['candidateTreasure']))
            from .presentation import markers_and_recommendations
            self._state['markedTreasure'],self._state['recommendedCells']=markers_and_recommendations(self._state['cells'],result['probabilities'],certain,self._state['predictedTreasure'],self._state['candidateTreasure'])
            import cv2,base64,numpy as np
            self._state['ghostItems']=[]
            for ghost in ghosts:
                mask=ghost['image'];rgba=np.zeros((*mask.shape,4),np.uint8);rgba[:,:,:3]=(70,190,250);rgba[:,:,3]=mask*255
                ok,png=cv2.imencode('.png',rgba)
                if ok:self._state['ghostItems'].append({k:ghost[k] for k in ('x','y','w','h','certain','support','pinned')}|{'source':'data:image/png;base64,'+base64.b64encode(png).decode('ascii')})

            if ghosts:self._state['status']+=' · 宝箱含轮廓推断'
            if candidates:self._state['status']+=f' · {len(candidates)} 个候选位置待验证'
            e=result['estimate'];g=result['guided']
            self._state['estimatePrimary']=f"约 {g['cost']} 镐子" if e else '无法估算'
            self._state['estimateDetails']=f" / {g['cells']} 格；随机参考 {e['cost']} 镐子" if e else ''
            self._state['estimate']=self._state['estimatePrimary']+self._state['estimateDetails']
            from .presentation import located_progress
            reliable_marks,_=markers_and_recommendations(self._state['cells'],result['probabilities'],certain,strong_predicted)
            progress=result.get('locationProgress') or located_progress(self._state['size'],self._state['shapes'],self._state['cells'],reliable_marks)
            from .presentation import pending_identified
            self._state['identifiedShapes']=result.get('identifiedShapes',[])
            self._state['pendingShapes']=pending_identified(self._state['shapes'],result['identifiedShapes']) if 'identifiedShapes' in result else progress['pendingShapes']
            self._state['allIdentified']=bool(self._state['shapes'] or self.completed_count) and not self._state['pendingShapes']
            self._state['allLocated']=bool((progress['complete'] or (self.completed_count and not self._state['shapes'])) and self.masks)
            self._state['locatedCells']=progress['locatedCells']
            self._state['markedTreasure'],self._state['recommendedCells']=markers_and_recommendations(self._state['cells'],result['probabilities'],certain,self._state['predictedTreasure'],self._state['candidateTreasure'],self._state['allIdentified'])
            self._state['completionScope']=sorted(set(self._state['predictedTreasure'])|set(certain))
            self._state['markedTreasure']=sorted(set(self._state['markedTreasure'])|set(self._state.get('completedTreasure',[])))
            if self._state['allIdentified']:
                self._state['probabilities']=[None]*len(self._state['cells'])
                self._state['recommendedCells']=[]
                remaining=max(0,sum(w*h*c for w,h,c in self._state['shapes'])-self._state['cells'].count(2))
                self._state.update(estimatePrimary=f"还需 {remaining*self._state['cost']} 镐子",estimateDetails=f" / {remaining} 格；已停止探索测算",estimate=f"还需 {remaining*self._state['cost']} 镐子 / {remaining} 格",status='宝物均已认出，位置仍待验证')
            if self._state['allLocated']:self.showLocated(progress['locatedCells'])
            elif self.overlay_window:self.overlay_window.publish({'size':self._state['size'],'cells':self._state['cells'][:],'probabilities':self._state['probabilities'],'certainTreasure':certain,'predictedTreasure':self._state['predictedTreasure'],'candidateTreasure':self._state['candidateTreasure'],'allIdentified':self._state['allIdentified'],'completedTreasure':self._state.get('completedTreasure',[]),'rect':self.observation.rect if self.observation else ()})
        self.changed.emit()

    def showLocated(self,located):
        remaining=sum(self._state['cells'][i]==0 for i in located)
        inferred=any(self._state['cells'][i]==0 and i not in self._state.get('certainTreasure',[]) for i in located)
        self.live['status']='宝物已全部定位'+('（含推断，请核对）' if inferred else '')+'，等待挖完'
        self._state.update(allLocated=True,allIdentified=True,pendingShapes=[],locatedCells=list(located),markedTreasure=sorted(set(located)|set(self._state.get('completedTreasure',[]))),candidateTreasure=[],recommendedCells=[],
            probabilities=[None]*len(self._state['cells']),
            estimatePrimary=f"还需 {remaining*self._state['cost']} 镐子",estimateDetails=f" / {remaining} 格；已停止探索测算",
            status='宝物已全部定位'+('（含推断，请核对）' if inferred else '')+'，等待挖完',
            estimate=f"还需 {remaining*self._state['cost']} 镐子 / {remaining} 格")
        if self.overlay_window:self.overlay_window.publish({'size':self._state['size'],'cells':self._state['cells'][:],
            'probabilities':self._state['probabilities'],'certainTreasure':self._state.get('certainTreasure',[]),
            'predictedTreasure':list(located),'completedTreasure':self._state.get('completedTreasure',[]),'rect':self.observation.rect if self.observation else ()})

    @Slot()
    def refreshDevices(self):
        if self.watcher:self.stopWatch()
        try:
            from fishing.windows import window_details
            self.devices=window_details();self.live['devices']=[f"{d['title'] or 'MuMu'} · PID {d['pid']}" for d in self.devices]
            self.live['deviceIndex']=min(self.live['deviceIndex'],max(0,len(self.devices)-1))
        except Exception as exc:self.devices=[];self.live['status']='刷新失败：'+str(exc)
        self.changed.emit()
    @Slot(int)
    def chooseDevice(self,index):
        if self.live['running']:return
        if 0<=index<len(self.devices):
            if index!=self.live['deviceIndex']:self.stopWatch()
            self.live['deviceIndex']=index;self.changed.emit()
    @Slot()
    def startWatch(self):
        if self.watcher is not None:return
        self.retry_timer.stop()
        self.live['running']=True
        if not getattr(self,'devices',[]):self.refreshDevices()
        if not self.devices:
            self.live['status']='未找到 MuMu，持续等待连接';self.changed.emit();self.retry_timer.start();return
        from .capture import Watcher
        from .overlay import Overlay
        self.generation+=1;hwnd=self.devices[self.live['deviceIndex']]['hwnd']
        if self.overlay_window is None:self.overlay_window=Overlay()
        self.overlay_window.bind(hwnd);self.overlay_window.active=self.live['overlay']
        self.watcher=Watcher(hwnd,self.generation);self.watcher.observed.connect(self.acceptObservation);self.watcher.boardSeen.connect(self.boardSeen);self.watcher.boardChanged.connect(self.boardChanged);self.watcher.status.connect(self.watchStatus);self.watcher.stopped.connect(self.watchStopped)
        self.live.update(running=True,status='正在连接 MuMu SDK…');self.changed.emit();self.watcher.start()
    @Slot()
    def stopWatch(self):
        self.retry_timer.stop()
        if self.watcher:self.watcher.stop();self.watcher=None
        self.generation+=1
        self.snapshot_ready=False;self.live.update(running=False,status='识别已停止');self.changed.emit()
        if self.overlay_window:self.overlay_window.active=False;self.overlay_window.hide()
    @Slot(int)
    def watchStopped(self,generation):
        if generation!=self.generation:return
        self.watcher=None;self.snapshot_ready=False
        if self.live['running']:
            self.live['status']='连接中断，正在重新连接…';self.devices=[];self.retry_timer.start()
        if self.overlay_window:self.overlay_window.active=False;self.overlay_window.hide()
        self.changed.emit()
    @Slot(int,str)
    def watchStatus(self,generation,message):
        if generation!=self.generation:return
        self.live['status']=message
        self.live['boardWarning']='未找到稳定棋盘，请前往棋盘页面' if '棋盘' in message and ('未找到' in message or '没有找到' in message) else ''
        self.live['unknownCells']=[];self.changed.emit()
        self.snapshot_ready=False
        if self.overlay_window:
            import time
            transient='未找到稳定棋盘' in message and time.monotonic()-self.overlay_window.updated<1.5
            if not transient:self.overlay_window.updated=0;self.overlay_window.setEnabled(False)
    @Slot(int)
    def boardSeen(self,generation):
        if generation==self.generation and (self.live['running'] or self.snapshot_ready) and self.overlay_window:
            self.overlay_window.heartbeat()

    @Slot(int)
    def boardChanged(self,generation):
        if generation!=self.generation:return
        self.snapshot_ready=False
        self.live['status']='棋盘变化，正在识别…'
        # Hold the last complete overlay while this board is settling/recalculating.
        if self.overlay_window:self.overlay_window.heartbeat()
        self.changed.emit()

    @Slot(bool)
    def setOverlay(self,value):
        self.live['overlay']=value
        if self.overlay_window:self.overlay_window.setEnabled(value and (self.live['running'] or self.snapshot_ready))
        self.changed.emit()
    @Slot()
    def resumeRecognition(self):
        self.dismissed_predictions=set();self.overrides={};self.pins={};self.last_key=None;self.live['autoConfig']=True;self.changed.emit()
    @Slot(int,object,object,object)
    def acceptObservation(self,generation,frame,observation,stage):
        if generation!=self.generation or not self.live['running']:return
        valid=self.applyObservation(frame,observation,stage)
        if self.overlay_window:
            if valid is False:self.overlay_window.updated=0
            else:self.overlay_window.heartbeat()
        if valid is not False:
            self.snapshot_ready=True
            if self.overlay_window:self.overlay_window.setEnabled(self.live['overlay'])
            self.changed.emit()
    def applyObservation(self,frame,observation,stage):
        from .vision import assign_templates
        new_session=stage.get('newSession',False) if isinstance(stage,dict) else False
        cost=stage.get('cost') if isinstance(stage,dict) else None
        stage=stage.get('stage') if isinstance(stage,dict) else stage
        previous=self.observation
        reversed_cells=previous is not None and previous.size==observation.size and any(a in (1,2) and b==0 for a,b in zip(previous.cells,observation.cells))
        stage_changed=stage is not None and self.last_key is not None and stage!=self._state['stage'] and self._state['stage']!=0
        if reversed_cells and not new_session and not stage_changed:
            candidate=(stage,observation.size,tuple(observation.cells))
            self.transition_count=self.transition_count+1 if candidate==self.transition_candidate else 1
            self.transition_candidate=candidate
            if self.transition_count<2:
                self.live.update(boardWarning='',status='正在确认新棋盘…');self.snapshot_ready=False;self.changed.emit();return False
            new_session=True
        else:self.transition_candidate=None;self.transition_count=0
        if new_session or stage_changed:
            # Manual corrections, retained treasure and completed counts belong to one board.
            self.live['autoConfig']=True
            self.selectStage(stage or self._state['stage'] or 1,internal=True)
            self.history=[];self._state['canUndo']=False
            self.transition_candidate=None;self.transition_count=0
        if self.live['autoConfig']:
            if stage is not None and self.presets[stage-1]['size']==observation.size:
                if stage!=self._state['stage'] or observation.size!=self._state['size']:
                    self.selectStage(stage,internal=True);self.board_key=stage
            elif observation.size!=self._state['size']:
                from .vision import infer_dimensions
                shapes=infer_dimensions(observation.silhouettes,observation.size,observation.tray)
                if not shapes:
                    self.live['status']='请按实际棋盘校正尺寸和宝物';self.live['configurationWarning']='宝物识别不完整，请修改尺寸与数量';self.changed.emit();return False
                costs={p['cost'] for p in self.presets if p['size']==observation.size}
                cost=next(iter(costs)) if len(costs)==1 else self._state['cost']
                self.overrides={};self.templates=[];self.last_key=None
                self._state.update(stage=0,size=observation.size,cost=cost,shapes=shapes,cells=[0]*(observation.size**2),treasureHistory=[],completedTreasure=[],completedSlots=[],trayShapes=[],completedGroups=[],unresolvedGround=[],completionScope=[],predictedTreasure=[],candidateTreasure=[],certainTreasure=[],markedTreasure=[])
        if observation.size!=self._state['size']:
            self.live['boardWarning']='识别尺寸与设置不符，请校正棋盘大小';self.live['status']='识别尺寸与手动配置不符，请校正';self.live['configurationWarning']='棋盘尺寸不符，请检查棋盘和宝物设置';self.changed.emit();return False
        self.live['boardWarning']=''
        self.live['unknownCells']=[i for i,v in enumerate(observation.cells) if v<0 and i not in observation.pending_cells and self._state['cells'][i] not in (1,2)]
        if cost is not None and self.live['autoConfig']:self._state['cost']=cost
        # Filled tray items are completed; solve only remaining treasures on late entry.
        completed_changed=False;remaining_templates=None
        # Scope must come from the previous board state, never from the disappearance itself.
        same_board=previous is not None and previous.size==observation.size and not new_session and not stage_changed
        predictions=set(self._state.get('completionScope',[]))|set(self._state.get('predictedTreasure',[]))|set(self._state.get('candidateTreasure',[]))
        scope=predictions|set(self._state.get('certainTreasure',[]))|set(self._state.get('markedTreasure',[]))
        scope.update(i for i,v in enumerate(self._state['cells']) if v==2)
        scope.update(i for i,v in self.overrides.items() if v==2)
        scope.difference_update(self.dismissed_predictions)
        scope.difference_update(i for i,v in self.overrides.items() if v!=2)
        archived_before=set(self._state.get('completedTreasure',[]))
        scope.difference_update(archived_before)
        if not same_board:scope.clear()
        from .capture import disappearance_groups
        vanished=set(observation.completed_cells)-archived_before
        if same_board:
            vanished.update(i for i,(old,new) in enumerate(zip(previous.cells,observation.cells)) if old==2 and new==1 and i not in observation.transient_cells and i not in archived_before)
        completed_ground=set();transient=set(observation.transient_cells)-archived_before
        # Filter before grouping: an unrelated cell must not bridge two treasure cells.
        for group in disappearance_groups(observation.size,vanished&scope):
            if len(group)>=2:completed_ground.update(group)
        transient.update(vanished-completed_ground);transient.difference_update(completed_ground)
        # An empty dig disproves a prediction unless actual joint disappearance proved it.
        if same_board:
            failed={i for i in predictions if previous.cells[i]==0 and observation.cells[i]==1 and i not in completed_ground}
            self.dismissed_predictions.update(failed)
        self._state['completionScope']=sorted(predictions-self.dismissed_predictions-completed_ground)
        recorded_groups=list(self._state.get('completedGroups',[]))
        unresolved=set(self._state.get('unresolvedGround',[]))
        known_shapes=self._state.get('trayShapes') or self._state['shapes']
        for group in disappearance_groups(observation.size,completed_ground):
            rows=[i//observation.size for i in group];cols=[i%observation.size for i in group]
            shape=tuple(sorted((max(cols)-min(cols)+1,max(rows)-min(rows)+1)))
            if len(group)==shape[0]*shape[1] and any(tuple(sorted((w,h)))==shape for w,h,count in known_shapes):
                footprint=sorted(group)
                if not any(g['cells']==footprint for g in recorded_groups):recorded_groups.append({'cells':footprint,'shape':list(shape)})
            else:unresolved.update(group)
        self._state['unresolvedGround']=sorted(unresolved)
        self._state['completedGroups']=recorded_groups
        items=observation.silhouettes
        slots=list(self._state.get('completedSlots',[]))
        def center(item):
            a,b,w,h=item['box'];return ((a+w/2)/observation.tray[2],(b+h/2)/observation.tray[3])
        completed_flags=[]
        for item in items:
            point=center(item) if observation.tray else None
            remembered=point is not None and any(abs(point[0]-sx)<.08 and abs(point[1]-sy)<.08 for sx,sy in slots)
            done=bool(item.get('completed') or remembered);completed_flags.append(done)
            if done and not remembered and point is not None:slots.append(point)
        if self.live['autoConfig'] and (any(completed_flags) or recorded_groups):
            # Match against the full tray catalog, not the already reduced remainder.
            catalogs=[self._state.get('trayShapes',[]),self._state['shapes']]
            known=stage or self._state['stage']
            if known and self.presets[known-1]['size']==observation.size:catalogs.append(self.presets[known-1]['shapes'])
            from .vision import infer_dimensions
            catalogs.append(infer_dimensions(items,observation.size,observation.tray))
            full=[]
            for shapes in catalogs:
                full=assign_templates(items,shapes)
                if full:break
            if full:
                from collections import Counter
                self._state['trayShapes']=copy.deepcopy(shapes);self._state['completedSlots']=slots
                ground_counts=Counter(tuple(g['shape']) for g in recorded_groups)
                color_counts=Counter(tuple(sorted((t['width'],t['height']))) for t,done in zip(full,completed_flags) if done)
                targets={shape:max(ground_counts[shape],color_counts[shape]) for shape in set(ground_counts)|set(color_counts)}
                extra={shape:max(0,count-color_counts[shape]) for shape,count in targets.items()}
                done_flags=completed_flags[:]
                for i,t in enumerate(full):
                    shape=tuple(sorted((t['width'],t['height'])))
                    if not done_flags[i] and extra.get(shape,0)>0:done_flags[i]=True;extra[shape]-=1
                remaining_templates=[t for t,done in zip(full,done_flags) if not done]
                dimensions=Counter(tuple(sorted((t['width'],t['height']))) for t in remaining_templates)
                self._state['shapes']=[[w,h,count] for (w,h),count in sorted(dimensions.items())]
                completed=sum(done_flags)
                completed_changed=completed>self.completed_count;self.completed_count=max(self.completed_count,completed)
                self.templates=remaining_templates
                if completed_changed:self.pins={};self._state['allLocated']=False
        if completed_changed:self._state['unresolvedGround']=[]
        self._state['completedCount']=self.completed_count
        self.live['completedTreasures']=self.completed_count
        cells=[self.overrides.get(i,v if v>=0 else self._state['cells'][i]) for i,v in enumerate(observation.cells)]
        # Within a stage, unknown/animation must not erase a previously opened tile.
        if self.last_key is not None:
            cells=[self.overrides.get(i,old if (old==2 and not (completed_changed and new==1)) or (old==1 and new==0) else new) for i,(old,new) in enumerate(zip(self._state['cells'],cells))]
        history=set(self._state.get('treasureHistory',[]))
        archived=set(self._state.get('completedTreasure',[]))
        # Preserve only observed joint disappearance, never an estimated footprint.
        archived.update(completed_ground);history.update(completed_ground)
        history.difference_update(transient)
        for i in transient:
            if self.overrides.get(i)!=2:cells[i]=1
        self.dismissed_predictions.update(transient)
        for i in archived:
            if self.overrides.get(i)==2:self.overrides.pop(i)
            if i not in self.overrides:cells[i]=1
        history.update(i for i,v in enumerate(cells) if v==2 and i not in transient)
        self._state.update(treasureHistory=sorted(history),completedTreasure=sorted(archived))
        templates=remaining_templates if remaining_templates is not None else assign_templates(observation.silhouettes,self._state['shapes'])
        derived=False
        if remaining_templates is None and not templates and observation.silhouettes and self.live['autoConfig']:
            from .vision import infer_dimensions
            shapes=infer_dimensions(observation.silhouettes,observation.size,observation.tray)
            if shapes:
                self._state['shapes']=shapes;templates=assign_templates(observation.silhouettes,shapes);derived=True
        self.live['derived']=self.live.get('derived',False) or derived
        self.live['configurationWarning']=(
            '宝物尺寸为估算，请核对尺寸与数量' if self.live['autoConfig'] and self.live['derived'] else
            '宝物识别不完整，请修改尺寸与数量' if self.live['autoConfig'] and self._state['shapes'] and not templates else '')
        key=(self._state['stage'],tuple(cells),tuple(tuple(s) for s in self._state['shapes']),self._state['cost'],bool(templates))
        self.observation=observation
        if remaining_templates==[]:self._state.update(templateCount=0,templatesPreview=[])
        if templates:
            if remaining_templates is None:self._state['trayShapes']=copy.deepcopy(self._state['shapes'])
            self.templates=templates;self._state['templateCount']=len(templates)
            if key!=self.last_key:
                import cv2,base64,numpy as np
                previews=[]
                for template in templates:
                    mask=template['mask'];rgba=np.zeros((*mask.shape,4),np.uint8);rgba[:,:,:3]=(65,90,107);rgba[:,:,3]=mask*255
                    ok,png=cv2.imencode('.png',rgba)
                    if ok:previews.append('data:image/png;base64,'+base64.b64encode(png).decode('ascii'))
                self._state['templatesPreview']=previews
        self.live['status']=f"已识别 {observation.size}×{observation.size} · {len(observation.silhouettes)} 件剪影"+(' · 朝向保留候选' if self.templates else ' · 剪影待校正')
        if stage is None:self.live['status']+=' · 请确认宝物配置与消耗'
        if observation.pending_cells:self.live['status']+=f' · {len(observation.pending_cells)} 格等待二次确认'
        elif self.live.get('derived'):self.live['status']+=' · 占格为剪影估算，请核对'
        if self.completed_count:self.live['status']+=f' · 已完成 {self.completed_count} 件（不再计入）'
        if key!=self.last_key:
            self.last_key=key;self._state['cells']=cells;self.invalidate()
            self.calculate()
        else:self.changed.emit()
    @Slot()
    def importImage(self):
        if self.imageBusy:return
        from PySide6.QtWidgets import QFileDialog
        path,_=QFileDialog.getOpenFileName(None,'导入寻宝截图','','图片 (*.png *.jpg *.jpeg *.bmp)')
        if path:self.loadImage(path)
    def loadImage(self,path):
        self.stopWatch();self.imageBusy=True
        self.live['status']='正在识别截图…';self.changed.emit()
        def work():
            try:
                import cv2,numpy as np
                from .vision import observe,read_stage,read_cost
                from rapidocr_onnxruntime import RapidOCR
                frame=cv2.imdecode(np.fromfile(path,dtype=np.uint8),cv2.IMREAD_COLOR)
                if frame is None:raise ValueError('图片无法读取')
                observation=observe(frame)
                if observation is None:raise ValueError('没有找到完整棋盘')
                ocr=RapidOCR(intra_op_num_threads=1,inter_op_num_threads=1)
                stage=read_stage(frame,observation.tray,ocr)
                self.imported.emit(frame,observation,{'stage':stage,'cost':read_cost(frame,observation.rect,ocr)},'')
            except Exception as exc:self.imported.emit(None,None,None,str(exc))
        threading.Thread(target=work,daemon=True).start()
    @Slot(object,object,object,str)
    def finishImport(self,frame,observation,stage,error):
        self.imageBusy=False
        if error:self.live['status']='导入失败：'+error;self.changed.emit();return
        self.last_key=None;self.overrides={};self.applyObservation(frame,observation,stage)
    def close(self):
        self.closing=True
        watcher=self.watcher
        self.stopWatch()
        if watcher and watcher.thread:watcher.thread.join(timeout=2)
        if self.solver_thread and self.solver_thread is not threading.current_thread():self.solver_thread.join(timeout=3)
        if self.overlay_window:self.overlay_window.close()

    @Slot(int,int,int,int)
    def pinTreasure(self,item,col,row,turn):
        if not 1<=item<=len(self.templates):
            self._state['pinStatus']='请先识别棋盘和宝物';self.changed.emit();return
        import numpy as np
        target=np.rot90(self.templates[item-1]['mask'],turn%4);h,w=target.shape[0]//32,target.shape[1]//32
        if not (1<=col<=self._state['size']-w+1 and 1<=row<=self._state['size']-h+1):
            self._state['pinStatus']='宝物超出棋盘边界';self.changed.emit();return
        self.checkpoint();self.pins[item-1]={'x':col-1,'y':row-1,'turn':turn%4}
        self._state['pinStatus']=f'已手动定位 {len(self.pins)} 件宝物';self.invalidate();self.calculate()
    @Slot()
    def clearPins(self):
        self.checkpoint();self.pins={};self._state['pinStatus']='已清除手动定位';self.invalidate();self.calculate()
