"""Qt boundary for clipboard import, corrections, and independent deployment."""
import json,queue,threading,shutil,logging,time
from dataclasses import asdict
from pathlib import Path
from PySide6.QtCore import QObject,Property,Signal,Slot,QTimer,QUrl,QBuffer,QIODevice,Qt
from PySide6.QtWidgets import QApplication,QFileDialog
from autotata.paths import ASSETS,ROOT
from .catalog import load_catalog
from .engine import Settings

MODES=('mumu_sdk','foreground','maatouch')


class LineupBackend(QObject):
    changed=Signal()
    devicesReady=Signal(int,object,str)
    def __init__(self,discover=True):
        super().__init__();self.settings=Settings();self.entries=[];self.generation=0
        self.cancel=threading.Event();self.worker=None;self.deploy_worker=None;self.stream=None;self.pending_auto=None
        self.events=queue.Queue();self.hotkeys=False;self.closing=False
        self.image=None;self.cells=[None]*25;self.details=[];self.overlay=None;self.grid_data=None
        self.file_dialog=None;self.window=None;self.popup_windows=None
        self.diagnostics=None;self.export_worker=None
        self.catalog=load_catalog();self.by_id={r['id']:r for r in self.catalog}
        self.source_path=ROOT/'lineup-reference.png'
        try:
            data=json.loads((ROOT/'lineup-settings.json').read_text(encoding='utf8'))
            self.settings=Settings(**{k:v for k,v in data.items() if k in asdict(self.settings)})
        except (OSError,ValueError,TypeError):pass
        if self.settings.mode not in MODES:self.settings.mode=MODES[0]
        for key in ('crop_top','crop_bottom'):
            if not isinstance(getattr(self.settings,key),int) or getattr(self.settings,key)<0:setattr(self.settings,key,0)
        self._state={'modeIndex':MODES.index(self.settings.mode),'devices':[],'deviceIndex':-1,'deviceText':'','refreshing':False,
            'running':False,'importing':False,'autoPending':False,'canClose':False,'source':'','sourceWidth':0,'sourceHeight':0,'columns':5,'rows':5,
            'status':'停留在游戏上阵界面，导入图片后自动识别并上阵','importStatus':'','completed':0,'inventoryFound':0,
            'count':None,'limit':None,'overlayEnabled':True,'issues':[],'outside':[],
            'exporting':False,'diagnosticHint':'自动保留最近20次记录，可导出后发送给开发者。',**asdict(self.settings)}
        self.devicesReady.connect(self.finishDevices)
        self.timer=QTimer(self);self.timer.setInterval(100);self.timer.timeout.connect(self.poll);self.timer.start()
        if discover:QTimer.singleShot(0,self.refresh)
    @Property('QVariantMap',notify=changed)
    def state(self):
        result=dict(self._state)
        reasons={r['sourceIndex']:r['reason'] for r in self._state['outside']}
        target_columns=self._state.get('grid',{}).get('columns',self._state['columns'])
        offset=(target_columns-self._state['columns'])//2
        for issue in self._state['issues']:
            row,col=divmod(issue['index'],target_columns);source_col=col-offset
            if 0<=source_col<self._state['columns']:reasons[row*self._state['columns']+source_col]=issue['reason']
        result['cells']=[{'id':k or '', 'name':self.by_id[k]['name'] if k in self.by_id else '待确认' if k=='?' else '',
            'image':QUrl.fromLocalFile(str(ASSETS/self.by_id[k]['imagePath'])).toString() if k in self.by_id else '',
            'stage':self.by_id[k]['stage'] if k in self.by_id else 0,'reason':reasons.get(index,'')} for index,k in enumerate(self.cells)]
        result['catalogCount']=len(self.catalog)
        return result
    def update(self,**values):
        self._state.update(values);self.changed.emit()
    def persist(self):
        try:(ROOT/'lineup-settings.json').write_text(json.dumps(asdict(self.settings),ensure_ascii=False,indent=2),encoding='utf8')
        except OSError:self.update(status='设置保存失败，请检查目录权限')
    def begin_diagnostics(self,rect=None):
        from .diagnostics import DiagnosticSession
        if self.diagnostics is not None:self.diagnostics.finish()
        try:
            self.diagnostics=DiagnosticSession(self.image,asdict(self.settings),root=self.source_path.parent)
            self.diagnostics.record('request',columns=self._state['columns'],rows=self._state['rows'],
                                    manualRect=list(rect) if rect else None,cells=list(self.cells),details=list(self.details))
        except Exception:
            self.diagnostics=None
            logging.getLogger('lineup').exception('Cannot start lineup diagnostics')
            self.update(diagnosticHint='诊断记录保存失败，请检查目录权限。')
        return self.diagnostics

    @Slot()
    def openDiagnostics(self):
        from PySide6.QtGui import QDesktopServices
        try:
            folder=self.source_path.parent/'logs/lineup-runs';folder.mkdir(parents=True,exist_ok=True)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve()))):raise OSError('无法打开目录')
        except OSError as exc:self.update(diagnosticHint='无法打开诊断目录：'+str(exc))

    @Slot()
    def exportDiagnostics(self):
        if self._state['running'] or self._state['importing'] or self._state['autoPending'] or self._state['exporting']:return
        if self.file_dialog is not None:self.file_dialog.raise_();self.file_dialog.activateWindow();return
        self.poll()
        from PySide6.QtCore import QStandardPaths
        directory=QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or str(Path.home())
        default=str(Path(directory)/('AutoTaTa-debug-'+time.strftime('%Y%m%d-%H%M%S')+'.zip'))
        dialog=QFileDialog(None,'导出诊断包',default,'ZIP 压缩包 (*.zip)')
        dialog.setOption(QFileDialog.DontUseNativeDialog,True)
        dialog.setFileMode(QFileDialog.AnyFile);dialog.setAcceptMode(QFileDialog.AcceptSave);dialog.setDefaultSuffix('zip')
        dialog.setWindowModality(Qt.NonModal);dialog.setObjectName('lineupExportDialog');self.file_dialog=dialog
        def finished(result):
            paths=dialog.selectedFiles() if result==QFileDialog.Accepted else []
            self.file_dialog=None;dialog.deleteLater()
            if not paths:return
            self.update(exporting=True,diagnosticHint='正在生成诊断包…')
            root=self.source_path.parent
            def work():
                try:
                    from .diagnostics import export_bundle
                    path=export_bundle(paths[0],root=root)
                    self.events.put({'exporting':False,'diagnosticHint':'诊断包已保存：'+str(path)})
                except Exception as exc:
                    logging.getLogger('lineup').exception('Diagnostic export failed')
                    self.events.put({'exporting':False,'diagnosticHint':'诊断包导出失败：'+str(exc)})
            self.export_worker=threading.Thread(target=work,daemon=True);self.export_worker.start()
        dialog.finished.connect(finished);dialog.show()
        if self.window:dialog.move(self.window.geometry().center()-dialog.rect().center())
        if self.popup_windows:self.popup_windows.track_dialog(dialog)
        dialog.activateWindow()
    @Slot(int)
    def setMode(self,index):
        if self._state['running'] or index not in range(len(MODES)):return
        self.settings.mode=MODES[index];self.update(modeIndex=index,deviceIndex=-1);self.persist();self.refresh()
    @Slot(int)
    def selectDevice(self,index):
        if not self._state['running'] and index in range(len(self.entries)):self.update(deviceIndex=index,deviceText=self._state['devices'][index])
    @Slot(str)
    def setAddress(self,text):
        if not self._state['running']:self.update(deviceIndex=-1,deviceText=text.strip())
    @Slot(str,'QVariant')
    def setValue(self,key,value):
        if key=='overlayEnabled':
            self.update(overlayEnabled=bool(value))
            if self.overlay:self.overlay.setEnabled(bool(value))
        elif key in ('crop_top','crop_bottom') and not self._state['running']:
            try:value=int(value)
            except (ValueError,TypeError):return
            if 0<=value<=3000:setattr(self.settings,key,value);self.update(**{key:value});self.persist()
    @Slot()
    def refresh(self):
        if self._state['running'] or self.closing:return
        self.generation+=1;generation=self.generation;mode=self.settings.mode;self.update(refreshing=True)
        def work():
            try:
                if mode=='maatouch':
                    from fishing.generic_adb import discover_adb_entries
                    entries=discover_adb_entries()
                else:
                    from fishing.windows import window_details
                    entries=window_details()
                self.devicesReady.emit(generation,entries,'')
            except Exception as exc:self.devicesReady.emit(generation,[],str(exc))
        threading.Thread(target=work,daemon=True).start()
    @Slot(int,object,str)
    def finishDevices(self,generation,entries,error):
        if generation!=self.generation or self.closing:return
        self.entries=entries;names=[e['title'] if self.settings.mode=='maatouch' else f"{e['title']} · {e['size'][0]}×{e['size'][1]} · PID {e['pid']}" for e in entries]
        self.update(devices=names,deviceIndex=0 if names else -1,deviceText=names[0] if names else '',refreshing=False)
        if error:self.update(status='设备发现失败：'+error)
        pending=self.pending_auto;self.pending_auto=None
        self.update(autoPending=False)
        if pending is not None and not error and not self.cancel.is_set() and not self.closing:self._start(pending)
    @Slot()
    def chooseImage(self):
        if self._state['running'] or self._state['importing']:return
        if self.file_dialog is not None:
            self.file_dialog.raise_();self.file_dialog.activateWindow();return
        dialog=QFileDialog(None,'选择阵容图片','','图片 (*.png *.jpg *.jpeg *.webp *.bmp)')
        dialog.setOption(QFileDialog.DontUseNativeDialog,True)
        dialog.setFileMode(QFileDialog.ExistingFile);dialog.setAcceptMode(QFileDialog.AcceptOpen)
        dialog.setWindowModality(Qt.NonModal);dialog.setObjectName('lineupFileDialog')
        self.file_dialog=dialog
        def finished(result):
            paths=dialog.selectedFiles() if result==QFileDialog.Accepted else []
            self.file_dialog=None;dialog.deleteLater()
            if paths:self.loadImage(paths[0])
        dialog.finished.connect(finished)
        dialog.show()
        if self.window:
            dialog.move(self.window.geometry().center()-dialog.rect().center())
        if self.popup_windows:self.popup_windows.track_dialog(dialog)
        dialog.activateWindow()
    @Slot(str)
    def loadImage(self,path):
        if self._state['running'] or self._state['importing']:return
        from .recognition import read_image
        path=QUrl(path).toLocalFile() if path.startswith('file:') else path
        try:
            file=Path(path)
            if file.stat().st_size>30*1024*1024:raise ValueError('图片过大，请使用 30 MB 以内的图片')
            image=read_image(file)
            if image is None:raise ValueError('无法读取图片')
            self.acceptImage(image)
        except (OSError,ValueError) as exc:self.update(status=str(exc))
    @Slot()
    def screenshot(self):
        if self._state['running'] or self._state['importing'] or self.closing:return
        try:
            from fishing.windows import start_screen_clip
            start_screen_clip()
        except Exception as exc:
            self.update(status='无法启动系统截图，请按 Win+Shift+S：'+str(exc))
        else:self.update(status='框选截图区域后，回到程序按 Ctrl+V 导入阵容')
    @Slot()
    def pasteImage(self):
        if self._state['running'] or self._state['importing']:return
        clipboard=QApplication.clipboard();mime=clipboard.mimeData()
        if mime is None:self.update(status='剪贴板中没有图片，可直接复制截图后粘贴');return
        if mime.hasImage():
            image=clipboard.image();buffer=QBuffer();buffer.open(QIODevice.WriteOnly)
            if image.isNull() or not image.save(buffer,'PNG'):
                self.update(status='无法读取剪贴板图片，请重新复制');return
            import cv2,numpy as np
            self.acceptImage(cv2.imdecode(np.frombuffer(bytes(buffer.data()),np.uint8),cv2.IMREAD_UNCHANGED))
        elif mime.hasUrls() and mime.urls()[0].isLocalFile():self.loadImage(mime.urls()[0].toLocalFile())
        else:self.update(status='剪贴板中没有图片，可直接复制截图后粘贴')
    def acceptImage(self,image):
        if self._state['exporting']:return
        import cv2,numpy as np
        if image is None or image.size==0 or image.shape[0]*image.shape[1]>20_000_000:
            self.update(status='图片尺寸不适合识别，请裁剪后再导入');return
        if image.ndim==2:image=cv2.cvtColor(image,cv2.COLOR_GRAY2BGR)
        if image.shape[2]==4:
            alpha=image[:,:,3:4].astype(float)/255
            image=(image[:,:,:3]*alpha+245*(1-alpha)).astype(np.uint8)
        self.image=image[:,:,:3];self.details=[];self.cells=[None]*(self._state['columns']*self._state['rows'])
        ok,png=cv2.imencode('.png',self.image)
        if not ok:self.update(status='预览图片保存失败');return
        try:self.source_path.write_bytes(png.tobytes())
        except OSError as exc:self.update(status='预览图片保存失败：'+str(exc));return
        self.update(source=QUrl.fromLocalFile(str(self.source_path)).toString()+'?v='+str(__import__('time').time_ns()),sourceWidth=image.shape[1],sourceHeight=image.shape[0],issues=[],outside=[],completed=0,inventoryFound=0)
        self.recognize([],auto_start=True)
    @Slot(int)
    def setColumns(self,columns):
        if columns not in (3,5) or self._state['running'] or self._state['importing']:return
        if self.pending_auto is not None:self.stop()
        rows=4 if columns==3 else 5
        self.cells=[None]*(columns*rows);self.update(columns=columns,rows=rows,issues=[],outside=[],status='阵型已切换，请重新识别或框选图片')
    @Slot('QVariantList')
    def recognize(self,rect,auto_start=False):
        if self.image is None or self._state['running'] or self._state['importing'] or self._state['exporting']:return
        if rect:
            if len(rect)!=4:return
            rect=tuple(map(float,rect));x,y,w,h=rect
            if min(w,h)<20 or min(x,y)<0 or x+w>self.image.shape[1]+1 or y+h>self.image.shape[0]+1:
                self.update(status='请框选图片中的完整阵型区域');return
        from .engine import FormationStream
        self.deploy_worker=None;self.pending_auto=None
        self.cancel=threading.Event();self.stream=FormationStream(len(self.cells));stream=self.stream
        self.cells=['?']*len(self.cells);self.details=[];self.grid_data=None
        diagnostic=self.begin_diagnostics(rect)
        if diagnostic:diagnostic.stage('recognition','running')
        self.update(importing=True,autoPending=False,status='正在识别阵容…',importStatus='正在定位阵型…');image=self.image.copy();columns=self._state['columns']
        def work():
            try:
                import cv2
                cv2.setNumThreads(1)
                from .vision import import_formation
                started=time.monotonic()
                details=[{'id':'?','score':0.,'candidates':[]} for _ in self.cells]
                def cell_ready(index,result,grid):
                    stream.put(index,result);details[index]=result
                    self.events.put({'partialImport':{'cells':stream.read()[0],'details':list(details),'grid':grid}})
                result=import_formation(image,columns,4 if columns==3 else 5,tuple(rect) if rect else None,
                    progress=lambda i,n:self.events.put({'importStatus':f'正在识别阵容 {i+1}/{n}'}),cancel=self.cancel,cell_ready=cell_ready)
                logging.getLogger('lineup').info('formation imported size=%sx%s grid=%s elapsed=%.3fs cells=%s uncertain=%s',
                    image.shape[1],image.shape[0],result['grid'].rect,time.monotonic()-started,result['cells'],
                    [{'index':i,**d} for i,d in enumerate(result['details']) if d['id']=='?'])
                if diagnostic:diagnostic.stage('recognition','partial' if '?' in result['cells'] else 'completed',grid=asdict(result['grid']),cells=result['cells'],details=result['details'])
                stream.finish(result);self.events.put({'importResult':result})
            except Exception as exc:
                if not self.cancel.is_set():
                    logging.getLogger('lineup').exception('Formation import failed size=%sx%s columns=%s manual_rect=%s',image.shape[1],image.shape[0],columns,rect)
                if diagnostic:diagnostic.stage('recognition','stopped' if self.cancel.is_set() else 'failed',error=str(exc))
                stream.fail(exc);self.events.put({'importError':str(exc)})
        self.worker=threading.Thread(target=work,daemon=True);self.worker.start()
        if auto_start:
            if self._state['refreshing']:
                self.pending_auto=stream;self.update(autoPending=True,status='正在查找上阵设备…')
            else:self._start(stream)
    @Slot(int,str)
    def setCell(self,index,identity):
        if self._state['running'] or self._state['importing'] or index not in range(len(self.cells)):return
        if identity not in self.by_id and identity not in ('','?'):return
        if self.pending_auto is not None:self.stop()
        self.cells[index]=identity or None;self.update(issues=[],outside=[])
    @Slot(str,result='QVariantList')
    def search(self,query):
        query=query.strip().lower()
        return [{'id':r['id'],'name':f"{r['name']} · T{r['stage']} · {r['element']} · {r['role']}",
            'image':QUrl.fromLocalFile(str(ASSETS/r['imagePath'])).toString()} for r in self.catalog if not query or query in r['name'].lower() or query in r['english'].lower()][:248]
    @Slot()
    def start(self):
        self._start()
    def _start(self,stream=None):
        if self.file_dialog is not None:return
        if self._state['running'] or (self._state['importing'] and stream is None) or self.closing or self._state['refreshing'] or self._state['exporting']:return
        if stream is not None:
            if self.cancel.is_set():return
            try:stream.read()
            except RuntimeError as exc:self.update(status=str(exc));return
        if stream is None and not any(k in self.by_id for k in self.cells):self.update(status='请先导入并确认阵容');return
        index=self._state['deviceIndex']
        if index in range(len(self.entries)):entry=self.entries[index]
        elif self.settings.mode=='maatouch' and self._state['deviceText']:
            adb=self.entries[0]['adb_path'] if self.entries else shutil.which('adb')
            if not adb:self.update(status='未找到 ADB，请安装模拟器并刷新设备');return
            entry={'hwnd':None,'adb_path':str(adb),'adb_address':self._state['deviceText']}
        else:self.update(status='请选择游戏设备后开始');return
        settings=Settings(**asdict(self.settings))
        if settings.mode=='maatouch':settings.adb_path=str(entry['adb_path']);settings.adb_address=entry['adb_address']
        if self.overlay is None:
            from .overlay import Overlay
            self.overlay=Overlay()
        self.overlay.bind(entry.get('hwnd'));self.overlay.publish({});self.overlay.setEnabled(self._state['overlayEnabled'])
        if stream is None:self.cancel=threading.Event()
        diagnostic=self.begin_diagnostics() if stream is None else self.diagnostics
        if diagnostic:diagnostic.stage('deployment','running')
        self.update(running=True,completed=0,issues=[],outside=[],inventoryFound=0,status='正在连接上阵设备…')
        from .runner import run
        def publish(value):
            if diagnostic:diagnostic.record('update',value=value)
            self.events.put(value)
        publish.diagnostics=diagnostic
        self.deploy_worker=threading.Thread(target=run,args=(entry.get('hwnd'),settings,stream if stream is not None else list(self.cells),self._state['columns'],self.cancel,publish),daemon=True);self.deploy_worker.start()
    @Slot()
    def stop(self):
        self.cancel.set();self.pending_auto=None;self.update(autoPending=False)
        if self._state['running'] or self._state['importing']:self.update(status='正在停止并释放操作…')
    @Slot()
    def close(self):
        if self.file_dialog is not None:self.file_dialog.reject()
        self.closing=True;self.stop()
        if self.overlay:self.overlay.setEnabled(False);self.overlay.close()
        self.poll()
    def poll(self):
        if self.hotkeys:
            from fishing.windows import user32
            from fishing.hotkeys import START_KEY,STOP_KEY
            if user32.GetAsyncKeyState(STOP_KEY)&1:self.stop()
            if user32.GetAsyncKeyState(START_KEY)&1:self.start()
        values={}
        while True:
            try:values.update(self.events.get_nowait())
            except queue.Empty:break
        partial=values.pop('partialImport',None)
        if partial:
            self.cells=partial['cells'];self.details=partial['details'];self.grid_data=asdict(partial['grid'])
        error=values.pop('importError',None)
        if error:values.update(status='已停止' if self.cancel.is_set() else error,importing=False)
        result=values.pop('importResult',None)
        if result:
            self.cells=result['cells'];self.details=result['details'];self.grid_data=asdict(result['grid'])
            summary=f"已识别 {sum(k in self.by_id for k in self.cells)} 只 · {self.cells.count('?')} 格待确认"
            values.update(importStatus=summary,importing=False)
            if self.deploy_worker is None and self.pending_auto is None:
                hint=self._state['status'] if '设备' in self._state['status'] else '点击格子可修正'
                values['status']=summary+'；'+hint
        if 'importStatus' in values and not self._state['running'] and self.deploy_worker is None and self.pending_auto is None and 'status' not in values:
            if '设备' not in self._state['status']:values['status']=values['importStatus']
        if values:self.update(**values)
        if self.overlay and self._state.get('grid'):
            self.overlay.publish({'grid':self._state['grid'],'issues':self._state['issues']});self.overlay.heartbeat()
        importing=self.worker is not None and self.worker.is_alive()
        deploying=self.deploy_worker is not None and self.deploy_worker.is_alive()
        if not importing and self._state['importing']:self.update(importing=False)
        if self.deploy_worker is not None and not deploying and self._state['running']:self.update(running=False)
        if self.diagnostics is not None and not self.diagnostics.closed and not importing and not deploying and self.pending_auto is None:
            self.diagnostics.record('final-ui',state={k:self._state[k] for k in ('status','importStatus','completed','count','limit','issues','outside')})
            self.diagnostics.finish('stopped' if self.cancel.is_set() else None)
        exporting=self.export_worker is not None and self.export_worker.is_alive()
        if self.closing and not importing and not deploying and not exporting:self.update(canClose=True)
