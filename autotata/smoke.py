import json
from pathlib import Path
from PySide6.QtCore import QTimer

def schedule(shell,destination,treasure_only,rafting_only=False,lineup_only=False):
    out=Path(destination);out.mkdir(parents=True,exist_ok=True)
    from . import __version__
    import sys
    report={'version':__version__,'title':shell.window.title(),'errors':[],'homeFeatureImports':[n for n in sys.modules if n in ('numpy','cv2','maa','fishing','treasure','rafting','lineup') or n.startswith(('fishing.','treasure.','maa.','rafting.','lineup.'))]}
    def check_frame(name,frame):
        state=frame.snapshot()
        report.setdefault('nativeFrames',{})[name]=state
        assert not state['errors'],state
        if state['enabled']:
            assert state['frameStyles'] and state['nativeRendering'] and state['opaque'] and not state['layered'],state
    def check_rafting():
        shell.nav.openRafting()
        backend=shell.nav.rafting;backend.persist=lambda:None
        original=list(backend.settings.priority)
        backend.moveReward(0,5)
        assert backend.settings.priority[-1]==original[0]
        backend.restoreRecommended()
        assert backend.settings.priority==[r['key'] for r in backend.state['rewards']]
        backend.setValue('boat_budget',37)
        assert backend.state['boat_budget']==37
        assert not backend.state['shutdown_on_stop']
        backend.setValue('boat_budget',0)
        backend.setValue('desired_multiplier',150)
        assert backend.state['desired_multiplier']==150
        assert backend.state['multipliers']==[1,2,3,5,10,20,50,100,150]
        backend.setValue('shutdown_force',True)
        assert backend.state['shutdown_force'] and not backend.state['shutdownPending']
        backend.setValue('shutdown_force',False)
        assert shell.window.property('baseWidth')==615
        report['rafting']={'rewards':len(backend.state['rewards']),'multipliers':backend.state['multipliers'],'multiplier':150,'title':shell.window.title(),'budget':backend.state['boat_budget'],'shutdownDefault':backend.state['shutdown_on_stop'],'forceShutdown':backend.state['shutdown_force'],'baseWidth':shell.window.property('baseWidth'),'baseHeight':shell.window.property('baseHeight')}
    def check_lineup():
        shell.nav.openLineup();backend=shell.nav.lineup;backend.persist=lambda:None
        assert len(backend.catalog)==248
        backend.setCell(6,'serrabloom');backend.setCell(7,'dozy');backend.setCell(11,'?')
        assert backend.cells[6]=='serrabloom' and backend.cells[11]=='?'
        assert len(backend.search(''))==248
        assert shell.window.property('baseWidth')==615
        report['lineup']={'catalog':len(backend.catalog),'cells':len(backend.cells),'baseWidth':615,'baseHeight':shell.window.property('baseHeight'),'title':shell.window.title()}
        backend.setColumns(3)
        assert backend.state['rows']==4 and len(backend.cells)==12
        report['lineup']['threeFour']={'columns':3,'rows':4,'cells':12,'limit':5}
        backend.setColumns(5);backend.setCell(6,'serrabloom');backend.setCell(7,'dozy');backend.setCell(11,'?')
        from PySide6.QtCore import QObject,QMetaObject,Q_ARG
        diagnostic_button=shell.window.findChild(QObject,'lineupExportDiagnostics')
        assert diagnostic_button is not None and diagnostic_button.property('enabled')
        report['lineup']['diagnostics']={'retainedRuns':20,'exportButton':True,'localOnly':True}
        editor=shell.window.findChild(QObject,'lineupEditor')
        assert QMetaObject.invokeMethod(editor,'openCell',Q_ARG('QVariant',6)) and editor.property('visible'), '修正窗口未打开'

    def check_lineup_editor():
        from PySide6.QtCore import QObject,Qt
        from PySide6.QtGui import QGuiApplication
        editor=shell.window.findChild(QObject,'lineupEditor')
        popup_window=next(w for w in QGuiApplication.allWindows() if w.metaObject().className()=='QQuickPopupWindow' and w.isVisible())
        assert popup_window is not shell.window
        assert editor.property('visible') and popup_window.transientParent() is shell.window
        state={'independentWindow':True,'width':popup_window.width(),'height':popup_window.height(),'nativeRendering':False}
        frame=shell.window_frame
        if frame.enabled:
            import ctypes
            from ctypes import wintypes
            handle=int(popup_window.winId());rendered=wintypes.BOOL()
            frame.dwm.DwmGetWindowAttribute(handle,1,ctypes.byref(rendered),ctypes.sizeof(rendered))
            style=frame.user.GetWindowLongPtrW(handle,-16)
            state.update(nativeRendering=bool(rendered.value),nativeCaption=(style&0x00C00000)==0x00C00000)
            assert state['nativeRendering'] and state['nativeCaption'],state
        popup_window.grabWindow().save(str(out/'packaged-lineup-editor.png'))
        from PySide6.QtCore import QMetaObject
        report['lineupEditor']=state;QMetaObject.invokeMethod(editor,'close')
    if lineup_only:
        def lineup_done():
            try:
                check_lineup_editor();shell.window.grabWindow().save(str(out/'packaged-lineup.png'));check_frame('lineup',shell.window_frame)
                report['errors']+=shell.errors;report['passed']=not report['errors']
            except Exception as exc:
                import traceback
                report['errors'].append(traceback.format_exc());report['passed']=False
            (out/'smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');shell.application.quit()
        def lineup_prepare():
            try:check_lineup()
            except Exception as exc:report['errors'].append(str(exc))
            QTimer.singleShot(200,lineup_done)
        QTimer.singleShot(500,lineup_prepare);return
    if rafting_only:
        def rafting_done():
            try:
                shell.window.grabWindow().save(str(out/'packaged-rafting.png'))
                check_frame('rafting',shell.window_frame)
                report['errors']+=shell.errors
                report['passed']=not report['errors']
            except Exception as exc:report['errors'].append(str(exc));report['passed']=False
            (out/'smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            shell.application.quit()
        def rafting_prepare():
            try:check_rafting()
            except Exception as exc:report['errors'].append(str(exc))
            QTimer.singleShot(200,rafting_done)
        QTimer.singleShot(500,rafting_prepare)
        return
    def done():
        try:
            if shell.treasure.busy:
                QTimer.singleShot(100,done);return
            layout={key:shell.window.property(key) for key in ('baseWidth','baseHeight','visualZoom')}
            layout.update(width=shell.window.width(),height=shell.window.height())
            report['treasureLayout']=layout
            check_frame('treasure',shell.window_frame)
            if layout['baseWidth']!=800 or abs(layout['height']-layout['baseHeight']*layout['visualZoom'])>1:
                report['errors'].append('Treasure page not proportionally fitted')
            shell.window.grabWindow().save(str(out/'packaged-treasure.png'))
            report['solver']=shell.treasure.state['status']
            report['estimate']=shell.treasure.state['estimate']
            report['errors']+=shell.errors
            if shell.nav.fishing:report['errors']+=shell.nav.fishing.qml_errors
            report['passed']=not report['errors'] and bool(shell.treasure.masks)
        except Exception as exc:report['errors'].append(str(exc));report['passed']=False
        (out/'smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        shell.application.quit()
    def check():
        try:
            shell.window.grabWindow().save(str(out/'packaged-home.png'))
            check_frame('home',shell.window_frame)
            if not treasure_only:
                check_lineup()
                QTimer.singleShot(200,after_lineup)
                return
            shell.nav.openTreasure()
            shell.treasure.calculate()
        except Exception as exc:report['errors'].append(str(exc))
        QTimer.singleShot(500,done)
    def after_lineup():
        try:
            shell.window.grabWindow().save(str(out/'packaged-lineup.png'));check_frame('lineup',shell.window_frame)
            check_lineup_editor()
            shell.nav.returnHome();check_rafting()
        except Exception as exc:report['errors'].append(str(exc))
        QTimer.singleShot(200,after_rafting)
    def after_rafting():
        try:
            shell.window.grabWindow().save(str(out/'packaged-rafting.png'))
            check_frame('rafting',shell.window_frame)
            layout={key:shell.window.property(key) for key in ('baseWidth','baseHeight','visualZoom')}
            assert abs(shell.window.height()-layout['baseHeight']*layout['visualZoom'])<=1
            report['rafting']['width']=shell.window.width()
            report['rafting']['height']=shell.window.height()
            shell.nav.returnHome()
            shell.nav.openFishing()
            if not shell.nav.fishing:raise RuntimeError('Fishing entry failed')
            check_frame('fishing',shell.nav.fishing.window_frame)
            shell.nav.fishing.backend.persist=lambda:None
            shell.nav.back()
            shell.nav.openTreasure()
            shell.treasure.calculate()
        except Exception as exc:report['errors'].append(str(exc))
        QTimer.singleShot(500,done)
    QTimer.singleShot(500,check)
