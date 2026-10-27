"""Small Qt loading window displayed before importing vision/input dependencies."""
import logging
import sys
import threading
from PySide6.QtCore import QObject, Signal, QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from .paths import ASSETS

from autotata.runtime import configure_graphics,center_window,close_boot_splash

def position_splash(window):
    # PyInstaller centers a 180-physical-pixel image on the full primary monitor.
    # Match its monitor, coordinate basis and DPI before showing our first frame.
    screen = QGuiApplication.primaryScreen()
    window.setScreen(screen)
    window.setProperty('pixelRatio', screen.devicePixelRatio())
    area = screen.geometry()
    window.setPosition(area.x() + (area.width()-window.width())//2,
                       area.y() + (area.height()-window.height())//2)

class Loader(QObject):
    loaded = Signal(object)
    failed = Signal(str)

    def load(self):
        try:
            from .gpu_app import GpuApp
            self.loaded.emit(GpuApp)
        except Exception:
            import traceback
            self.failed.emit(traceback.format_exc())

def main(discover=True, hotkeys=True, auto_quit_ms=None, smoke_path=None):
    from .log_policy import configure_logging
    maintenance = configure_logging()
    configure_graphics()
    application = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    application.setApplicationName('TaTaAutoFish')
    application.setWindowIcon(QIcon(str(ASSETS/'ui/rod-wood.png')))
    application.setQuitOnLastWindowClosed(False)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty('assetBase', QUrl.fromLocalFile(str(ASSETS.resolve())+'/').toString())
    engine.load(QUrl.fromLocalFile(str(ASSETS/'ui/Startup.qml')))
    if not engine.rootObjects():
        close_boot_splash()
        raise RuntimeError('启动界面加载失败')
    splash = engine.rootObjects()[0]
    splash.setProperty('iconSource',QUrl.fromLocalFile(str(ASSETS/'ui/rod-wood.png')).toString())
    position_splash(splash)
    splash.show()
    loader = Loader()
    state = {}

    def reveal():
        app = state['app']
        center_window(app.window)
        app.window.reveal()
        splash.close()
        application.setQuitOnLastWindowClosed(True)
        if smoke_path:
            def capture_smoke():
                import json
                from pathlib import Path
                from autotata import __version__
                out=Path(smoke_path);out.mkdir(parents=True,exist_ok=True)
                app.window.grabWindow().save(str(out/'packaged-fishing.png'))
                report={'version':__version__,'passed':not app.qml_errors,'errors':app.qml_errors,
                        'startupIcon':splash.property('iconSource'),'graphicsApi':str(app.window.rendererInterface().graphicsApi()),
                        'startButtonIcon':app.window.findChild(QObject,'startButton').property('iconSource').toString(),
                        'width':app.window.width(),'height':app.window.height()}
                frame=app.window_frame.snapshot()
                report['nativeFrame']=frame
                if frame['errors'] or (frame['enabled'] and not (frame['frameStyles'] and frame['nativeRendering'] and frame['opaque'] and not frame['layered'])):
                    report['errors'].append('Native Windows frame check failed: '+str(frame))
                    report['passed']=False
                (out/'smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                application.quit()
            QTimer.singleShot(700,capture_smoke)
        if auto_quit_ms is not None:
            QTimer.singleShot(auto_quit_ms, application.quit)

    def ready(app_type):
        try:
            state['app'] = app_type(discover=discover, hotkeys=hotkeys, animate_startup=True)
            # Play the complete one-shot gesture once UI creation has released the GUI thread.
            QTimer.singleShot(80, splash.finish)
        except Exception:
            import traceback
            failed(traceback.format_exc())

    def failed(message):
        logging.error('Startup failed: %s', message)
        close_boot_splash()
        splash.setProperty('errorText', '启动失败，请查看 logs/session.log')
        QTimer.singleShot(6000, application.quit)

    def begin():
        close_boot_splash()
        state['thread'] = threading.Thread(target=loader.load, name='Startup imports', daemon=True)
        state['thread'].start()

    loader.loaded.connect(ready)
    loader.failed.connect(failed)
    splash.finished.connect(reveal)
    QTimer.singleShot(80, begin)
    try:
        return application.exec()
    finally:
        close_boot_splash()
        if 'app' in state:
            state['app'].backend.timer.stop()
        logging.shutdown()
        maintenance.close()
