import QtQuick
import QtQuick.Window
Window {
    id: splash
    width: 260; height: 280; visible: false; color: "transparent"
    flags: Qt.SplashScreen | Qt.FramelessWindowHint
    property bool treasureGesture: featureKind==="treasure"
    signal finished()
    function finish() { if(treasureGesture)treasureBeat.restart();else fishingSway.restart() }
    Item {
        id: artwork; objectName: "featureArtwork"; width: 180; height: 180; anchors.centerIn: parent
        Image { objectName: "featureStartupIcon"; anchors.fill: parent; source: assetBase+(splash.treasureGesture ? "ui/treasure.png" : featureKind==="lineup" ? "ui/lineup.svg" : featureKind==="rafting" ? "ui/rafting.png" : "ui/rod-wood.png"); fillMode: Image.PreserveAspectFit; smooth: true; mipmap: true }
    }
    SequentialAnimation {
        id: treasureBeat
        ParallelAnimation {
            NumberAnimation { target: artwork; property: "rotation"; from: 0; to: -19; duration: 130; easing.type: Easing.OutCubic }
            SequentialAnimation {
                NumberAnimation { target: artwork; property: "scale"; from: 1; to: 1.17; duration: 70; easing.type: Easing.OutCubic }
                NumberAnimation { target: artwork; property: "scale"; to: 1.03; duration: 90; easing.type: Easing.InOutCubic }
            }
        }
        ParallelAnimation {
            NumberAnimation { target: artwork; property: "rotation"; to: 19; duration: 170; easing.type: Easing.OutCubic }
            SequentialAnimation {
                NumberAnimation { target: artwork; property: "scale"; to: 1.23; duration: 75; easing.type: Easing.OutCubic }
                NumberAnimation { target: artwork; property: "scale"; to: 1.04; duration: 95; easing.type: Easing.InOutCubic }
            }
        }
        ParallelAnimation {
            NumberAnimation { target: artwork; property: "rotation"; to: 0; duration: 180; easing.type: Easing.OutCubic }
            NumberAnimation { target: artwork; property: "scale"; to: 1.12; duration: 180; easing.type: Easing.OutCubic }
            NumberAnimation { target: splash; property: "opacity"; to: 0; duration: 180; easing.type: Easing.InCubic }
        }
        ScriptAction { script: splash.finished() }
    }
    SequentialAnimation {
        id: fishingSway
        NumberAnimation { target: artwork; property: "rotation"; to: -12; duration: 250; easing.type: Easing.InOutSine }
        NumberAnimation { target: artwork; property: "rotation"; to: 12; duration: 400; easing.type: Easing.InOutSine }
        ParallelAnimation {
            NumberAnimation { target: artwork; property: "rotation"; to: 0; duration: 350; easing.type: Easing.InOutSine }
            NumberAnimation { target: artwork; property: "scale"; to: 1.18; duration: 350; easing.type: Easing.InOutCubic }
            NumberAnimation { target: splash; property: "opacity"; to: 0; duration: 350; easing.type: Easing.InOutCubic }
        }
        ScriptAction { script: splash.finished() }
    }
}
