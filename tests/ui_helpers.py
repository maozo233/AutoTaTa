"""Send test events to the actual Qt window hosting a control."""
from PySide6.QtCore import QPointF,Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest


def find_item(window,name):
    def walk(node):
        if node is None:return None
        if node.objectName()==name:return node
        for child in node.childItems():
            result=walk(child)
            if result is not None:return result
    result=walk(window.contentItem())
    if result is not None:return result
    for other in QGuiApplication.allWindows():
        if other.isVisible() and other.metaObject().className()=='QQuickPopupWindow':
            result=walk(other.property('contentItem'))
            if result is not None:return result


def popup_window(popup):
    content=popup.property('contentItem')
    center=content.mapToGlobal(QPointF(content.width()/2,content.height()/2)).toPoint()
    for window in QGuiApplication.allWindows():
        if window.isVisible() and window.metaObject().className()=='QQuickPopupWindow' and window.geometry().contains(center):return window
    raise AssertionError('Popup has no independent window')


def click_item(owner,node):
    point=node.mapToGlobal(QPointF(node.width()/2,node.height()/2)).toPoint()
    target=owner
    for window in QGuiApplication.allWindows():
        if window.isVisible() and window.metaObject().className()=='QQuickPopupWindow' and window.geometry().contains(point):target=window;break
    QTest.mouseClick(target,Qt.LeftButton,Qt.NoModifier,point-target.position())
