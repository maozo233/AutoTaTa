import QtQuick
import QtQuick.Controls.Basic
TextField {
    id: control
    property var colorTheme: null
    property string helpText: ""
    height: 29
    font.family: "Chiron GoRound TC"
    font.weight: Font.Bold
    font.pixelSize: 13
    color: colorTheme ? colorTheme.ink : "#101d42"
    leftPadding: 10
    rightPadding: 8
    selectByMouse: true
    selectionColor: colorTheme ? colorTheme.highlight : "#b9e8fa"
    selectedTextColor: "#101d42"
    renderType: Text.QtRendering
    opacity: enabled ? 1 : 0.6
    hoverEnabled: true
    background: Rectangle {
        radius: 6; antialiasing: true
        color: control.colorTheme ? (control.activeFocus || control.hovered ? control.colorTheme.surface : control.colorTheme.white) : control.activeFocus ? "#edfaff" : control.hovered ? "#f5fcff" : "white"
        border.width: control.activeFocus ? 1.8 : 1.2
        border.color: control.colorTheme ? (control.activeFocus ? control.colorTheme.focus : control.colorTheme.border) : control.activeFocus ? "#12a9e0" : "#39659b"
        Behavior on color { ColorAnimation { duration: 140; easing.type: Easing.OutCubic } }
        Behavior on border.color { ColorAnimation { duration: 140; easing.type: Easing.OutCubic } }
    }
    HelpTip { parent: control; text: control.helpText; visible: control.helpText.length>0 && control.hovered && !control.activeFocus }
}
