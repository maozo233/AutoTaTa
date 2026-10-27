import QtQuick
Rectangle {
    id: notice
    property string text: ""
    property string guidance: ""
    property bool emphasis: true
    property real iconPixels: 18
    property bool centeredText: false
    property real textRightPadding: 8
    implicitHeight: emphasis ? Math.max(32,message.implicitHeight+12) : 16
    radius: 6; antialiasing: true
    color: emphasis ? "#dd4131" : "transparent"
    border.color: emphasis ? "#ac2b20" : "transparent"
    border.width: 0
    Image {
        objectName: notice.objectName+"Icon"
        x: 8; anchors.verticalCenter: parent.verticalCenter
        width: notice.iconPixels; height: width
        visible: notice.emphasis
        source: assetBase+"ui/warning.svg"; fillMode: Image.PreserveAspectFit
        sourceSize: Qt.size(48,48); smooth: true
    }
    HintText {
        id: message; objectName: notice.objectName+"Text"
        x: notice.emphasis ? 31 : 0
        width: parent.width-x-(notice.emphasis ? notice.textRightPadding : 0)
        y: notice.guidance ? (notice.centeredText ? (parent.height-33)/2 : 3) : 0
        height: notice.guidance ? (notice.centeredText ? 18 : parent.height-21) : parent.height
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment: notice.centeredText ? Text.AlignHCenter : Text.AlignLeft
        text: notice.text; helpText: text; wrapMode: Text.Wrap
        color: notice.emphasis ? "#ffffff" : "#806447"
        font.pixelSize: notice.emphasis ? 12 : 10
        font.weight: notice.emphasis ? Font.Black : Font.Medium
    }
    HintText {
        objectName: notice.objectName+"Guidance"
        x: notice.emphasis ? 31 : 0
        y: notice.centeredText ? message.y+message.height : parent.height-18
        width: parent.width-x-notice.textRightPadding; height: 15; visible: notice.guidance!==""
        horizontalAlignment: notice.centeredText ? Text.AlignHCenter : Text.AlignLeft
        text: notice.guidance; color: notice.emphasis ? "#ffffff" : "#806447"
        font.pixelSize: 10; font.weight: Font.Medium
    }
}
