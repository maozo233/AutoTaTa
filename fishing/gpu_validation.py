"""Offline GPU UI interaction checks. No emulator input or live hotkeys."""
import time
from PySide6.QtCore import QObject, QPointF, QPoint, Qt, QMetaObject, QLoggingCategory, qInstallMessageHandler
from PySide6.QtTest import QTest
from PySide6.QtGui import QFontDatabase
from .gpu_app import GpuApp, MODE_LABELS
from .paths import settings_path
from .engine import Settings

# Keep the window alive while the caller verifies Win32 controller DLLs.
_test_app=None

def validate_gpu_ui(report):
    global _test_app
    path=settings_path();saved=path.read_bytes() if path.exists() else None
    messages=[]
    QLoggingCategory.setFilterRules('qt.scenegraph.general=true\nqt.rhi.general=true')
    old_handler=qInstallMessageHandler(lambda kind,context,message:messages.append(message))
    app=GpuApp(discover=False,hotkeys=False);_test_app=app
    try:
        QTest.qWait(300)
        report['graphics_api']=str(app.window.rendererInterface().graphicsApi())
        assert 'Direct3D11' in report['graphics_api']
        report['msaa_samples']=app.window.format().samples()
        assert report['msaa_samples']==4
        report['bundled-font-families']=[QFontDatabase.applicationFontFamilies(i) for i in app.font_ids]
        assert all(report['bundled-font-families'])
        control=app.window.findChild(QObject,'resizeGrip')
        assert control is not None
        frame_times=[]
        app.window.frameSwapped.connect(lambda:frame_times.append(time.perf_counter()))
        choices=[];update_times=[]
        app.backend.worker=type('Worker',(),{'is_alive':lambda self:True})()
        app.backend.session_settings=Settings(rod_budget=123,desired_multiplier=20)
        app.backend.update(running=True,rod_budget=123,desired_multiplier=20,catchCount=9,rodsUsed=18)
        app.window.setPosition(20,20)
        for factor in (.5,.75,1.,1.25,1.5):
            start=time.perf_counter();app.backend.resizeTo(factor);update_times.append((time.perf_counter()-start)*1000)
            QTest.qWait(230)
            point=control.mapToScene(QPointF(control.width()/2,control.height()/2))
            assert control.isVisible() and 0<point.x()<app.window.width() and 0<point.y()<app.window.height(),factor
            initial=app.window.property('visualZoom')
            target=QPoint(round(point.x()+(1.-initial)*615),round(point.y()+(1.-initial)*app.window.property('baseHeight')))
            QTest.mousePress(app.window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(round(point.x()),round(point.y())))
            QTest.mouseMove(app.window,target,25)
            QTest.qWait(40)
            QTest.mouseRelease(app.window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,target)
            QTest.qWait(230)
            assert abs(app.backend.state['ui_scale']-1.)<.005,(factor,app.backend.state['ui_scale'])
            assert abs(app.window.width()/app.window.height()-615/app.window.property('baseHeight'))<.004
            assert control is app.window.findChild(QObject,'resizeGrip')
            assert app.window.findChild(QObject,'zoomPicker') is None
            assert app.backend.state['desired_multiplier']==20 and app.backend.state['rod_budget']==123
            assert not app.window.findChild(QObject,'startButton').property('enabled')
            assert app.window.findChild(QObject,'multiplierPicker').property('enabled')
            choices.append({'from':factor,'dragged_back_to':app.backend.state['ui_scale']})
        for name in ('modePicker','budgetField','baitLimitField','cropTopField','cropBottomField','autoBaitSwitch','buffEndSwitch','stopBaitSwitch','devicePicker','shutdownSwitch','forceShutdownSwitch'):
            assert app.window.findChild(QObject,name).property('enabled'),name
        report['settings-editable-during-run']=True
        app.backend.setValue('desired_multiplier',3)
        assert app.backend.session_updates.get_nowait()==3
        assert app.backend.state['catchCount']==9 and app.backend.state['rodsUsed']==18
        app.backend.stop();assert app.backend.cancel.is_set()
        app.backend.worker=type('Worker',(),{'is_alive':lambda self:False})()
        app.backend.events.put('准备钓鱼 | 已完成 10 次 | 本次用竿 20/123 根')
        app.backend.events.put('已停止')
        app.backend.poll();assert app.backend.state['catchCount']==10 and app.backend.state['rodsUsed']==20
        assert not app.backend.state['running']
        switch=app.window.findChild(QObject,'autoBaitSwitch')
        app.backend.update(auto_bait=False);QTest.qWait(30)
        point=switch.mapToScene(QPointF(18,14))
        QTest.mouseClick(app.window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(round(point.x()),round(point.y())))
        QTest.qWait(200);assert app.backend.state['auto_bait']
        begin=switch.mapToScene(QPointF(28,14));end=switch.mapToScene(QPointF(5,14))
        QTest.mousePress(app.window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(round(begin.x()),round(begin.y())))
        QTest.mouseMove(app.window,QPoint(round(end.x()),round(end.y())),25)
        QTest.mouseRelease(app.window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(round(end.x()),round(end.y())))
        QTest.qWait(200);assert not app.backend.state['auto_bait']
        report['bait-switch-click-and-drag']=True
        app.backend.resizeTo(.5);QTest.qWait(220)
        picker=app.window.findChild(QObject,'modePicker')
        point=picker.mapToScene(QPointF(picker.width()/2,picker.height()/2))
        QTest.mouseClick(app.window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(round(point.x()),round(point.y())))
        QTest.qWait(50)
        assert app.window.property('modeMenuVisible') and abs(app.window.property('modeMenuScale')-.5)<.01
        QTest.keyClick(app.window,Qt.Key.Key_Escape)
        app.backend.resizeTo(1.);QTest.qWait(220)
        report['dropdown-follows-window-scale']=True
        app.backend.warning.emit('窗口提示','测试提示，关闭后继续。')
        QTest.qWait(100)
        dialog=app.window.findChild(QObject,'warningDialog')
        assert dialog.property('visible')
        QMetaObject.invokeMethod(dialog,'accept');QTest.qWait(100)
        assert not dialog.property('visible')
        assert not any('Component is not ready' in m for m in messages),messages
        report['warning-dialog-and-tooltip-style']=True
        assert not app.qml_errors,app.qml_errors
        report['proportional-drag-resize-from-five-scales']=choices
        report['zoom-reuses-existing-controls']=True
        report['running-settings-and-counters-preserved']=True
        report['runtime-multiplier-queue-and-stop']=True
        report['zoom-handler-ms']=update_times
        report['animation-frames-presented']=len(frame_times)
        assert len(frame_times)>20
        report['three-input-modes']=list(MODE_LABELS.values())
        report['qml-errors']=app.qml_errors
        report['graphics-diagnostics']=messages
        report['ui_size']=[app.window.width(),app.window.height()]
        hwnd=int(app.window.winId())
        app.backend.closeRequested();QTest.qWait(30)
        assert app.backend.state['canClose'] and not app.window.isVisible()
        report['close-after-interactions']=True
        return hwnd
    finally:
        app.backend.timer.stop()
        if saved is not None:path.write_bytes(saved)
        elif path.exists():path.unlink()
        qInstallMessageHandler(old_handler)
