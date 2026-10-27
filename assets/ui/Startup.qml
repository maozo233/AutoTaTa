import QtQuick
import QtQuick.Window
Window {
    id: splash
    property real pixelRatio: 1
    property string iconSource: assetBase+"app-icon.png"
    width: 260/pixelRatio; height: 280/pixelRatio
    visible: false
    color: "transparent"
    flags: Qt.SplashScreen | Qt.FramelessWindowHint
    property string errorText: ""
    signal finished()
    function finish() { exitAnimation.start() }
    Item {
        id: artwork
        objectName: "loadingArtwork"
        width: 180/splash.pixelRatio; height: 180/splash.pixelRatio
        anchors.centerIn: parent
        Image {
            anchors.fill: parent
            objectName: "startupIcon"
            source: splash.iconSource
            fillMode: Image.PreserveAspectFit
            smooth: true; mipmap: true
        }
    }
    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom; anchors.bottomMargin: 4
        text: splash.errorText; color: "#223152"; font.pixelSize: 12
    }
    SequentialAnimation {
        id: exitAnimation
        // One 1-second gesture: left, right, then home while fading out.
        NumberAnimation { target: artwork; property: "rotation"; from: 0; to: -12; duration: 250; easing.type: Easing.InOutSine }
        NumberAnimation { target: artwork; property: "rotation"; from: -12; to: 12; duration: 400; easing.type: Easing.InOutSine }
        ParallelAnimation {
            NumberAnimation { target: artwork; property: "rotation"; from: 12; to: 0; duration: 350; easing.type: Easing.InOutSine }
            NumberAnimation { target: artwork; property: "scale"; to: 1.18; duration: 350; easing.type: Easing.InOutCubic }
            NumberAnimation { target: splash; property: "opacity"; to: 0; duration: 350; easing.type: Easing.InOutCubic }
        }
        ScriptAction { script: splash.finished() }
    }
}
