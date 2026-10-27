import QtQuick
Rectangle {
    id: badge
    property string detail: ""
    width: 112; height: 24; radius: 5; antialiasing: true
    visible: !!detail; color: "#dd4131"; border.color: "#ac2b20"; border.width: 0
    Row { anchors.centerIn: parent; height: 20; spacing: 5
        Image { width: 18; height: 18; anchors.verticalCenter: parent.verticalCenter; source: assetBase+"ui/warning.svg"; sourceSize: Qt.size(48,48) }
        LabelText { height: 20; text: "识别待校正"; font.pixelSize: 13; font.weight: Font.Black; color: "#ffffff"; helpText: badge.detail }
    }
}
