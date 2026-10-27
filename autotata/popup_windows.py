"""Native decoration for Qt Quick's independent popup windows."""
from PySide6.QtCore import QObject,Slot,QEvent,Qt,QTimer
from PySide6.QtGui import QGuiApplication
from .window_frame import WindowFrame


class PopupWindows(QObject):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.frames={}
        self.dialogs={}
        app=QGuiApplication.instance()
        app.installEventFilter(self)
        app.applicationStateChanged.connect(self.application_changed)

    def track_dialog(self,dialog):
        key=id(dialog);self.dialogs[key]=dialog
        dialog.destroyed.connect(lambda *_,key=key:self.dialogs.pop(key,None))

    def application_changed(self,state):
        if state!=Qt.ApplicationActive:
            for dialog in list(self.dialogs.values()):
                if dialog.isVisible():dialog.reject()

    def eventFilter(self,watched,event):
        # Decoration must not wait for Popup.opened, which follows its render
        # transition and can be delayed while another full-screen app is active.
        if event.type()==QEvent.Show and watched.metaObject().className()=='QQuickPopupWindow':
            QTimer.singleShot(0,self.decorate)
        if event.type() in (QEvent.MouseButtonPress,QEvent.NonClientAreaMouseButtonPress):
            point=event.globalPosition().toPoint()
            for dialog in list(self.dialogs.values()):
                if dialog.isVisible() and not dialog.frameGeometry().contains(point):
                    dialog.reject();return True
        return False

    @Slot()
    def decorate(self):
        # Use QWindow wrappers from the application. PySide's QQuickItem.window()
        # conversion is invalid for Qt's private QQuickPopupWindow subclass.
        for window in QGuiApplication.allWindows():
            if window.metaObject().className()!='QQuickPopupWindow' or not window.isVisible():continue
            key=id(window)
            if key not in self.frames:
                self.frames[key]=WindowFrame(window,popup=True)
                window.destroyed.connect(lambda *_,key=key:self.forget(key))
            self.frames[key].apply()

    def forget(self,key):
        frame=self.frames.pop(key,None)
        if frame is not None:
            try:frame.close()
            except RuntimeError:pass  # Qt may already have destroyed its surface.
