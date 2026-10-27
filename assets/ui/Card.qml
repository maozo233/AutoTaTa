import QtQuick
Item {
    id: card
    property var colorTheme: null
    property real panelTop: 5
    property real titleTop: 0
    property real panelRightInset: 5
    property string title: ""
    property string icon: ""
    property color accent: "#47d1ff"
    default property alias contents: body.data
    Rectangle { x: 4; y: card.panelTop+5; width: parent.width-card.panelRightInset+1; height: card.colorTheme ? parent.height-card.panelTop : parent.height-10; radius: 18; color: card.colorTheme ? card.colorTheme.shadow : "#45bddc"; antialiasing: true }
    Rectangle { x: 1; y: card.panelTop; width: parent.width-card.panelRightInset; height: card.colorTheme ? parent.height-card.panelTop : parent.height-10; radius: 17; color: card.colorTheme ? card.colorTheme.surface : "#fffef5"; border.color: "#101d42"; border.width: 2.3; antialiasing: true }
    Rectangle {
        visible: card.title!==""; x: 7; y: card.titleTop; width: 143; height: 29; radius: 15
        color: card.accent; border.color: "#101d42"; border.width: 2.3; antialiasing: true
        Rectangle { x: 6; y: 4; width: parent.width-12; height: 9; radius: 5; color: card.colorTheme ? card.colorTheme.white : "white"; opacity: .32; antialiasing: true }
        Image { x: card.colorTheme ? 10.3 : 8; anchors.verticalCenter: parent.verticalCenter; width: 21; height: 21; source: card.icon; fillMode: Image.PreserveAspectFit; smooth: true; mipmap: true; sourceSize: Qt.size(64,64) }
        LabelText { x: card.colorTheme ? 39.3 : 37; y: 3; height: 23; text: card.title; font.pixelSize: 15; color: "white"; style: Text.Outline; styleColor: "#101d42" }
    }
    Item { id: body; x: 17; y: card.title!=="" ? 34 : 13; width: card.width-37; height: card.height-y-14 }
}
