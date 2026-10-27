import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
ComboBox {
    id: control
    property var colorTheme: null
    property string helpText: ""
    height: 29
    font.family: "Chiron GoRound TC"
    font.weight: Font.Bold
    font.pixelSize: 12
    hoverEnabled: true
    leftPadding: 10; rightPadding: 24
    topPadding: 0; bottomPadding: 0
    opacity: enabled ? 1 : 0.6
    contentItem: Text {
        text: control.displayText; font: control.font; color: "#101d42"
        verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
        renderType: Text.QtRendering; antialiasing: true
    }
    indicator: Text {
        x: control.width-20; anchors.verticalCenter: parent.verticalCenter
        text: "▾"; font.pixelSize: 14; color: "#101d42"; renderType: Text.QtRendering
    }
    background: Rectangle {
        radius: 6; antialiasing: true
        color: control.colorTheme ? (control.down || control.hovered ? control.colorTheme.surface : control.colorTheme.white) : control.down ? "#d8f4ff" : control.hovered ? "#f1fbff" : "white"
        border.width: control.activeFocus ? 1.8 : 1.2
        border.color: control.colorTheme ? (control.activeFocus ? control.colorTheme.focus : control.colorTheme.border) : control.activeFocus ? "#12a9e0" : "#39659b"
        Behavior on color { ColorAnimation { duration: 140; easing.type: Easing.OutCubic } }
    }
    delegate: ItemDelegate {
        required property var modelData
        required property int index
        objectName: "pickerOption"+index
        width: ListView.view ? ListView.view.width : control.popup.availableWidth
        leftPadding: Math.max(5,10*control.popup.uiScale); rightPadding: Math.max(5,8*control.popup.uiScale)
        topPadding: 0; bottomPadding: 0
        height: Math.max(24,28*control.popup.uiScale,contentItem.implicitHeight+8*control.popup.uiScale)
        highlighted: control.highlightedIndex===index
        contentItem: Text {
            objectName: "pickerOptionText"+index
            text: modelData; color: "#101d42"; font.family: control.font.family; font.weight: control.font.weight; font.pixelSize: Math.max(10,control.font.pixelSize*control.popup.uiScale)
            wrapMode: Text.Wrap; verticalAlignment: Text.AlignVCenter
            renderType: Text.QtRendering; antialiasing: true
        }
        background: Rectangle { color: control.colorTheme ? (parent.highlighted ? control.colorTheme.refresh : control.colorTheme.surface) : parent.highlighted ? "#d4efff" : "#fffef5"; radius: 4; antialiasing: true }
    }
    popup: NativePopup {
        objectName: control.objectName.length ? control.objectName+"Popup" : "pickerPopup"
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
        property real uiScale: control.Window.window ? control.Window.window.visualZoom : 1
        x: 0; y: control.height+3; implicitWidth: control.width*uiScale; width: implicitWidth
        implicitHeight: Math.min(Math.max(menu.contentHeight,control.count*Math.max(24,28*uiScale))+2*padding,Math.max(120,240*uiScale))
        padding: 4*uiScale
        contentItem: ListView {
            id: menu
            clip: true; implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            highlightMoveDuration: 0
            boundsBehavior: Flickable.StopAtBounds
            ScrollIndicator.vertical: ScrollIndicator {}
        }
        background: PopupSurface {}
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 100; easing.type: Easing.OutCubic } }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 80 } }
    }
    HelpTip { parent: control; text: control.helpText; visible: control.helpText.length>0 && control.hovered && !control.popup.visible }
}
