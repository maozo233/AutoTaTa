"""Shared Qt configuration; no feature modules or device APIs."""
from PySide6.QtGui import QGuiApplication,QSurfaceFormat
from PySide6.QtQuick import QQuickWindow,QSGRendererInterface
from PySide6.QtQuickControls2 import QQuickStyle
_configured=False
def configure_graphics():
    global _configured
    if _configured:return
    QQuickStyle.setStyle('Basic');QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Direct3D11)
    fmt=QSurfaceFormat();fmt.setSamples(4);QSurfaceFormat.setDefaultFormat(fmt);_configured=True
def center_window(window):
    screen=window.screen() or QGuiApplication.primaryScreen();area=screen.availableGeometry()
    window.setPosition(area.x()+(area.width()-window.width())//2,area.y()+(area.height()-window.height())//2)
def close_boot_splash():
    import os
    if not os.environ.get('_PYI_SPLASH_IPC'):return
    try:
        import pyi_splash
        pyi_splash.close()
    except ImportError:pass
