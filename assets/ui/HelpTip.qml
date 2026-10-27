import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
ToolTip {
    id: tip
    objectName: "helpTip"
    popupType: Popup.Window
    delay: 550
    timeout: -1
    padding: 10
    margins: 8
    width: Math.min(contentItem.implicitWidth+leftPadding+rightPadding, 260, parent && parent.Window.window ? parent.Window.window.width-24 : 260)
    contentItem: Text {
        text: tip.text
        color: "#101d42"
        font.family: "Chiron GoRound TC"
        font.weight: Font.Medium
        font.pixelSize: 12
        lineHeightMode: Text.FixedHeight
        lineHeight: 18
        wrapMode: Text.Wrap
        renderType: Text.QtRendering
        antialiasing: true
    }
    background: PopupSurface {}
    Connections {
        target: tip
        function onOpened() { Qt.callLater(function() { if(tip.visible)popupWindows.decorate() }) }
    }
    Connections { target: Qt.application; function onStateChanged() { if(Qt.application.state!==Qt.ApplicationActive)tip.close() } }
    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 140; easing.type: Easing.OutCubic } }
    exit: Transition { NumberAnimation { property: "opacity"; to: 0; duration: 90; easing.type: Easing.InOutCubic } }
}
