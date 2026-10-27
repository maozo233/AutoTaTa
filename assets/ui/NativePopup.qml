import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
Popup {
    id: popup
    popupType: Popup.Window
    transformOrigin: Popup.TopLeft
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    property bool centerInOwner: false
    readonly property var ownerWindow: parent ? parent.Window.window : null
    Connections {
        target: popup
        function onOpened() {
            Qt.callLater(function() {
                if(popup.visible && popup.contentItem.Window.window)
                    popupWindows.decorate()
                if(popup.visible && popup.centerInOwner)centering.restart()
            })
        }
        function onWidthChanged() { if(popup.visible && popup.centerInOwner)centering.restart() }
        function onHeightChanged() { if(popup.visible && popup.centerInOwner)centering.restart() }
    }
    Timer {
        id: centering; interval: 20
        onTriggered: if(popup.visible && popup.centerInOwner) {
            popup.x=(popup.parent.width-popup.width)/2
            popup.y=(popup.parent.height-popup.height)/2
        }
    }
    Connections { target: popup.ownerWindow; function onVisibleChanged() { if(!target.visible)Qt.callLater(function(){popup.close()}) } }
    Connections { target: Qt.application; function onStateChanged() { if(Qt.application.state!==Qt.ApplicationActive)Qt.callLater(function(){popup.close()}) } }
}
