import QtQuick
import QtQuick.Controls.Basic
Switch {
    id: control
    property string helpText: ""
    width: 85; height: 28; padding: 0
    property string statusText: checked ? "已开启" : "已关闭"
    hoverEnabled: true
    indicator: Rectangle {
        opacity: control.enabled ? 1 : .55
        x: 0; y: (control.height-height)/2; width: 38; height: 21; radius: 11
        color: control.checked ? "#6cdc24" : "#788698"
        border.color: control.checked ? "#345837" : "#48536c"; border.width: 1.5; antialiasing: true
        Behavior on color { ColorAnimation { duration: 180; easing.type: Easing.InOutCubic } }
        Rectangle {
            x: 3+control.visualPosition*16; y: 3; width: 15; height: 15; radius: 8; color: "#faffff"; antialiasing: true
            Behavior on x { enabled: !control.down; NumberAnimation { duration: 180; easing.type: Easing.InOutCubic } }
            scale: control.down ? 1.08 : 1
            Behavior on scale { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }
        }
    }
    contentItem: HintText { text: control.statusText; opacity: control.enabled || control.checked ? 1 : .55; color: control.checked ? "#101d42" : "#597499"; leftPadding: 43; font.pixelSize: 10; font.family: "Chiron GoRound TC"; font.weight: control.checked ? Font.Bold : Font.Medium; lineHeightMode: Text.FixedHeight; lineHeight: 15 }
    HelpTip { parent: control; text: control.helpText; visible: control.helpText.length>0 && control.hovered && !control.down }
}
