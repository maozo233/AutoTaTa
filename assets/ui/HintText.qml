import QtQuick
Text {
    id: label
    property string helpText: ""
    color: "#597499"
    font.family: "Chiron GoRound TC"
    font.weight: Font.Medium
    font.pixelSize: 11
    renderType: Text.QtRendering
    antialiasing: true
    verticalAlignment: Text.AlignVCenter
    HoverHandler { id: helpHover; enabled: label.helpText.length>0 }
    HelpTip { parent: label; text: label.helpText; visible: helpHover.hovered && label.helpText.length>0 }
}
