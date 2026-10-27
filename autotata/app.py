"""Lightweight home; feature modules and device discovery load only on entry."""
import sys,threading
from PySide6.QtCore import QObject,Signal,Slot,QUrl,QTimer
from PySide6.QtGui import QGuiApplication,QFontDatabase,QIcon
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from .paths import ASSETS
from .runtime import configure_graphics,center_window
from . import __version__

class Imports(QObject):
    ready=Signal(str,object)
    failed=Signal(str)
    def load(self,kind):
        try:
            if kind=='fishing':
                from fishing.gpu_app import GpuApp
                feature=GpuApp
            elif kind=='rafting':
                from rafting.backend import RaftingBackend
                feature=RaftingBackend
            elif kind=='lineup':
                from lineup.backend import LineupBackend
                feature=LineupBackend
            else:
                from treasure.backend import TreasureBackend
                feature=TreasureBackend
            self.ready.emit(kind,feature)
        except Exception:
            import traceback
            self.failed.emit(traceback.format_exc())

class Navigation(QObject):
    message=Signal(str)
    def __init__(self,shell,discover=True,animations=True):
        super().__init__();self.shell=shell;self.app=shell.application;self.discover=discover;self.animations=animations
        self.fishing=None;self.treasure=None;self.rafting=None;self.lineup=None;self.home=None;self.closing=False;self.loading=False;self.kind=None
        self.splash_engine=None;self.splash=None;self.import_thread=None
        self.imports=Imports(self);self.imports.ready.connect(self.prepare);self.imports.failed.connect(self.failed)
        self.timer=QTimer(self);self.timer.setInterval(100);self.timer.timeout.connect(self.poll)
    @Slot()
    def openFishing(self):self.launch('fishing')
    @Slot()
    def openTreasure(self):self.launch('treasure')
    @Slot()
    def openRafting(self):self.launch('rafting')
    @Slot()
    def openLineup(self):self.launch('lineup')
    def launch(self,kind):
        if self.loading or self.closing:return
        self.loading=True;self.kind=kind
        if self.animations:
            self.splash_engine=QQmlApplicationEngine()
            self.splash_engine.warnings.connect(lambda errors:self.shell.errors.extend(e.toString() for e in errors))
            context=self.splash_engine.rootContext();context.setContextProperty('assetBase',QUrl.fromLocalFile(str(ASSETS.resolve())+'/').toString());context.setContextProperty('featureKind',kind)
            self.splash_engine.load(QUrl.fromLocalFile(str(ASSETS/'ui/FeatureStartup.qml')))
            if not self.splash_engine.rootObjects():self.failed('功能启动界面加载失败');return
            self.splash=self.splash_engine.rootObjects()[0]
            self.splash.setScreen(self.home.screen());center_window(self.splash);self.splash.show()
            self.splash.finished.connect(self.commit)
            QTimer.singleShot(60,lambda:self.begin(kind))
        else:self.begin(kind)
    def begin(self,kind):
        if self.closing:return
        cached=getattr(self,kind)
        if cached is not None:self.finishLoading();return
        if self.animations:
            self.import_thread=threading.Thread(target=self.imports.load,args=(kind,),name=kind+' imports',daemon=True);self.import_thread.start()
        else:
            try:
                if kind=='fishing':
                    from fishing.gpu_app import GpuApp
                    self.prepare(kind,GpuApp)
                elif kind=='rafting':
                    from rafting.backend import RaftingBackend
                    self.prepare(kind,RaftingBackend)
                elif kind=='lineup':
                    from lineup.backend import LineupBackend
                    self.prepare(kind,LineupBackend)
                else:
                    from treasure.backend import TreasureBackend
                    self.prepare(kind,TreasureBackend)
            except Exception as exc:self.failed(str(exc))
    @Slot(str,object)
    def prepare(self,kind,feature):
        if self.closing:return
        try:
            if kind=='fishing':
                self.fishing=feature(discover=self.discover,hotkeys=False,animate_startup=self.animations)
                self.fishing.window.setProperty('embedded',True)
                self.fishing.window.backRequested.connect(self.back)
                self.fishing.backend.changed.connect(self.checkClosed)
            elif kind=='rafting':
                self.rafting=feature(discover=self.discover)
                self.rafting.window=self.home
                self.shell.engine.rootContext().setContextProperty('rafting',self.rafting)
                self.home.setProperty('raftingLoaded',True)
            elif kind=='lineup':
                self.lineup=feature(discover=self.discover)
                self.lineup.window=self.home;self.lineup.popup_windows=self.shell.popup_windows
                self.shell.engine.rootContext().setContextProperty('lineup',self.lineup)
                self.home.setProperty('lineupLoaded',True)
            else:
                self.treasure=feature(discover=self.discover)
                self.app.aboutToQuit.connect(self.treasure.close)
                self.shell.engine.rootContext().setContextProperty('treasure',self.treasure)
                self.home.setProperty('treasureLoaded',True)
            self.finishLoading()
        except Exception as exc:self.failed(str(exc))
    def finishLoading(self):
        if self.animations:QTimer.singleShot(40,self.splash.finish)
        else:self.commit()
    @Slot()
    def commit(self):
        if self.closing:return
        if self.kind=='fishing':
            self.fishing.backend.hotkeys=self.discover
            center_window(self.fishing.window)
            if self.animations:self.fishing.window.reveal()
            else:self.fishing.window.show()
            self.home.hide()
        elif self.kind=='rafting':
            self.rafting.hotkeys=self.discover
            if self.animations:self.home.showRafting()
            else:self.home.setProperty('page','rafting');self.home.show()
            center_window(self.home)
        elif self.kind=='lineup':
            self.lineup.hotkeys=self.discover
            if self.animations:self.home.showLineup()
            else:self.home.setProperty('page','lineup');self.home.show()
            center_window(self.home)
        else:
            if self.animations:self.home.showTreasure()
            else:self.home.setProperty('page','treasure');self.home.show()
            center_window(self.home)
        self.loading=False
        if self.splash:self.splash.close()
        # The engine owns its QML window; delete together after the finished signal.
        if self.splash_engine:self.splash_engine.deleteLater()
        self.splash=None;self.splash_engine=None
    @Slot(str)
    def failed(self,message):
        import logging
        logging.error('Feature startup failed: %s',message)
        self.loading=False
        if self.splash:self.splash.close()
        if self.splash_engine:self.splash_engine.deleteLater()
        self.splash=None;self.splash_engine=None
        self.message.emit('功能加载失败：'+message)
        if self.shell.treasure_only or self.shell.rafting_only or self.shell.lineup_only:self.home.show()
    @Slot()
    def returnHome(self):
        if self.lineup and (self.lineup.state['running'] or self.lineup.state['importing']):
            self.message.emit('请先停止上阵或图片识别，再返回主页。');return
        if self.lineup and self.lineup.overlay:self.lineup.overlay.setEnabled(False)
        if self.rafting and (self.rafting.state['running'] or self.rafting.state['shutdownPending']):
            self.message.emit('请先停止漂流或取消关机倒计时，再返回主页。');return
        self.home.showHome()
    @Slot()
    def back(self):
        if self.fishing.backend.state['running'] or self.fishing.backend.state['shutdownPending']:
            self.fishing.backend.warning.emit('返回主页','请先停止钓鱼或取消关机倒计时。');return
        self.fishing.backend.hotkeys=False;self.fishing.window.hide();self.returnHome()
    @Slot()
    def ensureWindowVisible(self):
        window=self.home
        if window is None:return
        area=window.screen().availableGeometry()
        # Expanding optional sections can change the fitted size after initial centering.
        window.setPosition(max(area.x(),min(window.x(),area.right()+1-window.width())),
                           max(area.y(),min(window.y(),area.bottom()+1-window.height())))
    @Slot(str)
    def pageChanged(self,page):
        if self.rafting:self.rafting.hotkeys=self.discover and page=='rafting'
        if self.lineup:self.lineup.hotkeys=self.discover and page=='lineup'
    def checkClosed(self):
        if self.fishing.backend.state['canClose']:
            if self.closing:self.poll()
            else:self.close()
    @Slot()
    def close(self):
        self.closing=True
        if self.treasure:self.treasure.stopWatch()
        if self.rafting:self.rafting.close()
        if self.lineup:self.lineup.close()
        if self.fishing:self.fishing.backend.closeRequested()
        self.timer.start();self.poll()
    def poll(self):
        if (not self.fishing or self.fishing.backend.state['canClose']) and (not self.rafting or self.rafting.state['canClose']) and (not self.lineup or self.lineup.state['canClose']):self.timer.stop();self.app.quit()

class Shell:
    def __init__(self,discover=True,treasure_only=False,animations=True,rafting_only=False,lineup_only=False):
        configure_graphics();self.treasure_only=treasure_only;self.rafting_only=rafting_only;self.lineup_only=lineup_only
        self.application=QGuiApplication.instance() or QApplication(sys.argv[:1])
        self.application.setQuitOnLastWindowClosed(False);self.application.setWindowIcon(QIcon(str(ASSETS/('ui/lineup.png' if lineup_only else 'app.ico'))));self.application.setApplicationName('AutoTaTa')
        for weight in ('500M','700B','900H'):QFontDatabase.addApplicationFont(str(ASSETS/'fonts'/f'ChironGoRoundTC-{weight}.ttf'))
        self.errors=[];self.nav=Navigation(self,discover,animations);self.engine=QQmlApplicationEngine()
        from .popup_windows import PopupWindows
        self.popup_windows=PopupWindows(self.application)
        self.engine.rootContext().setContextProperty('popupWindows',self.popup_windows)
        self.engine.warnings.connect(lambda errors:self.errors.extend(e.toString() for e in errors))
        for name,value in {'nav':self.nav,'appVersion':__version__,'treasureOnly':treasure_only,'raftingOnly':rafting_only,'lineupOnly':lineup_only,'assetBase':QUrl.fromLocalFile(str(ASSETS.resolve())+'/').toString()}.items():self.engine.rootContext().setContextProperty(name,value)
        self.engine.load(QUrl.fromLocalFile(str(ASSETS/'ui/AutoTaTa.qml')))
        if not self.engine.rootObjects():raise RuntimeError(str(self.errors))
        self.window=self.engine.rootObjects()[0];self.nav.home=self.window;center_window(self.window)
        from .window_frame import WindowFrame
        self.window_frame=WindowFrame(self.window)
        if treasure_only:QTimer.singleShot(0,self.nav.openTreasure)
        if rafting_only:QTimer.singleShot(0,self.nav.openRafting)
        if lineup_only:QTimer.singleShot(0,self.nav.openLineup)
    @property
    def treasure(self):return self.nav.treasure

def main(treasure_only=False,rafting_only=False,lineup_only=False):
    from .log_policy import configure_logging
    maintenance=configure_logging()
    try:
        smoke='--smoke-test' in sys.argv
        shell=Shell(discover=not smoke,treasure_only=treasure_only,animations=not smoke,rafting_only=rafting_only,lineup_only=lineup_only)
        from .runtime import close_boot_splash
        close_boot_splash()
        if smoke:
            from autotata.smoke import schedule
            schedule(shell,sys.argv[sys.argv.index('--smoke-test')+1],treasure_only,rafting_only,lineup_only)
        return shell.application.exec()
    finally:maintenance.close()
