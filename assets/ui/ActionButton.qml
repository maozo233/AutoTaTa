import QtQuick
import QtQuick.Controls.Basic
Button {
    id: control
    property var colorTheme: null
    property color tone: colorTheme ? colorTheme.refresh : "#bdb6ee"
    property color shadowTone: colorTheme ? colorTheme.buttonShadow : "#3798bb"
    property string shortcut: ""
    property url iconSource: ""
    property bool large: false
    property bool centeredLabel: false
    property real iconPixels: large ? 37 : 15
    property real keyPulse: 0
    function pulse() { keyAnimation.restart() }
    height: large ? 52 : 29
    padding: 0
    leftPadding: 8
    rightPadding: colorTheme ? 8 : large ? 24 : 12
    topPadding: 0
    bottomPadding: colorTheme ? 0 : 5
    hoverEnabled: true
    scale: down || keyPulse>0 ? 0.975 : 1
    Behavior on scale { NumberAnimation { duration: 130; easing.type: Easing.OutCubic } }
    opacity: enabled ? 1 : 0.55
    SequentialAnimation { id: keyAnimation; NumberAnimation { target: control; property: "keyPulse"; to: 1; duration: 70 } NumberAnimation { target: control; property: "keyPulse"; to: 0; duration: 180; easing.type: Easing.OutCubic } }
    background: Item {
        Rectangle { x: 3; y: 4; width: control.colorTheme ? parent.width : parent.width-3; height: control.colorTheme ? parent.height : parent.height-4; radius: control.large ? 26 : 14; color: control.shadowTone; antialiasing: true }
        Rectangle {
            width: control.colorTheme ? parent.width : parent.width-4; height: control.colorTheme ? parent.height : parent.height-5; radius: control.large ? 24 : 13
            color: control.hovered ? Qt.lighter(control.tone,1.08) : control.tone
            border.color: control.colorTheme ? control.colorTheme.ink : "#101d42"; border.width: control.large ? 2.8 : 2.2; antialiasing: true
            Behavior on color { ColorAnimation { duration: 150; easing.type: Easing.OutCubic } }
            Rectangle { anchors.fill: parent; anchors.margins: control.colorTheme ? 4 : 6; radius: control.large ? 20 : 9; color: "transparent"; border.width: 3; border.color: control.colorTheme ? control.colorTheme.highlight : "#ddf5ff"; opacity: 0.6; antialiasing: true }
            Rectangle { x: 13; y: 7; width: parent.width-26; height: control.large ? 7 : 4; radius: 4; color: control.colorTheme ? control.colorTheme.white : "white"; opacity: 0.45; antialiasing: true }
        }
    }
    contentItem: Item {
        Item {
            anchors.left: parent.left
            anchors.right: !control.centeredLabel && shortcutBadge.visible ? shortcutBadge.left : parent.right
            anchors.rightMargin: !control.centeredLabel && shortcutBadge.visible ? 8 : 0
            height: parent.height
            Row {
                anchors.centerIn: parent
                spacing: control.iconSource.toString()!=="" && control.text!=="" ? (control.large ? 10 : 5) : 0
                Image {
                    visible: control.iconSource.toString()!==""
                    source: control.iconSource
                    anchors.verticalCenter: parent.verticalCenter
                    width: control.iconPixels; height: width
                    fillMode: Image.PreserveAspectFit; smooth: true; mipmap: true
                    sourceSize: Qt.size(width*2,height*2)
                }
                LabelText {
                    visible: control.text!==""
                    anchors.verticalCenter: parent.verticalCenter
                    text: control.text; font.pixelSize: control.large ? 22 : 12
                    font.preferTypoLineMetrics: true
                    style: control.large ? Text.Outline : Text.Normal
                    styleColor: "#101d42"; color: control.large ? "white" : "#101d42"
                }
            }
        }
        Rectangle {
            id: shortcutBadge
            objectName: "shortcutBadge"
            visible: control.shortcut!==""; width: control.shortcut==="PgDown" ? 61 : 48; height: 31
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            anchors.rightMargin: control.centeredLabel ? -4 : 0
            radius: 5; color: "#edf7ff"; border.color: "#4b648c"; border.width: 1.5; antialiasing: true
            LabelText { anchors.centerIn: parent; text: control.shortcut; font.family: "Chiron GoRound TC"; font.weight: Font.Bold; font.pixelSize: 11; font.preferTypoLineMetrics: true }
        }
    }
}
