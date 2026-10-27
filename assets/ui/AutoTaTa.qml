import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Window
Window {
    id: root
    objectName: "autoTaTaWindow"
    property string page: "home"
    property bool treasureLoaded: false
    property bool raftingLoaded: false
    property bool lineupLoaded: false
    property real featureScale: 1
    function showTreasure() { page="treasure"; opacity=0; featureScale=.98; show(); featureEntrance.restart() }
    function showRafting() { page="rafting"; opacity=0; featureScale=.98; show(); featureEntrance.restart() }
    function showLineup() { page="lineup"; opacity=0; featureScale=.98; show(); featureEntrance.restart() }
    function showHome() { featureEntrance.stop(); page="home"; opacity=1; featureScale=1; show() }
    ParallelAnimation { id: featureEntrance; NumberAnimation { target: root; property: "opacity"; to: 1; duration: 220; easing.type: Easing.OutCubic } NumberAnimation { target: root; property: "featureScale"; to: 1; duration: 220; easing.type: Easing.OutCubic } }
    Binding { target: root.contentItem; property: "scale"; value: root.featureScale }
    Binding { target: root.contentItem; property: "transformOrigin"; value: Item.Center }
    CampTheme { id: campTheme }
    LineupTheme { id: lineupTheme }
    readonly property var pageTheme: page==="treasure" ? campTheme : page==="lineup" ? lineupTheme : null
    readonly property real baseWidth: page==="home" || page==="rafting" || page==="lineup" ? 615 : 800
    readonly property real baseHeight: page==="home" ? 740 : page==="lineup" ? lineupPage.y+lineupPage.naturalHeight+12 : page==="rafting" ? raftingPage.y+raftingPage.naturalHeight+12 : treasurePage.y+treasurePage.naturalHeight+28
    property real treasureZoom: 1
    property bool resizing: false
    readonly property real maxZoom: Math.min(2, (Screen.desktopAvailableWidth-40)/baseWidth, (Screen.desktopAvailableHeight-40)/baseHeight)
    readonly property real minZoom: Math.min(.5, maxZoom*.75)
    readonly property real visualZoom: page==="home" ? Math.min(1,maxZoom) : Math.max(minZoom,Math.min(maxZoom,treasureZoom))
    width: Math.round(baseWidth*visualZoom); height: Math.round(baseHeight*visualZoom)
    minimumWidth: Math.floor(baseWidth*minZoom); minimumHeight: Math.floor(baseHeight*minZoom)
    onWidthChanged: Qt.callLater(nav.ensureWindowVisible)
    onHeightChanged: Qt.callLater(nav.ensureWindowVisible)
    visible: !treasureOnly && !raftingOnly && !lineupOnly; color: pageTheme ? pageTheme.canvas : "#e9edf7"; flags: Qt.Window | Qt.FramelessWindowHint
    title: page==="home" ? "AutoTaTa "+appVersion+" by maozo" : page==="lineup" ? "TaTaLineup by maozo" : page==="rafting" ? "TaTaRafting by maozo" : "TaTaTreasure by maozo"
    onPageChanged: { nav.pageChanged(page) }
    onClosing: function(event) { event.accepted=false; nav.close() }
    Item {
        id: scene; objectName: "scaledScene"
        width: root.baseWidth; height: root.baseHeight
        scale: root.visualZoom; transformOrigin: Item.TopLeft
        Rectangle { anchors.fill: parent; color: root.pageTheme ? root.pageTheme.canvas : "#e9edf7"; radius: root.pageTheme ? 15 : 18; antialiasing: true }
        Item {
            id: header; x: root.page==="home" ? 16 : 12; y: 8; width: parent.width-2*x; height: 42
            MouseArea { anchors.fill: parent; onPressed: root.startSystemMove() }
            ActionButton { colorTheme: root.pageTheme; visible: root.page!=="home" && !treasureOnly && !raftingOnly && !lineupOnly; width: 85; height: 38; text: "返回"; tone: root.pageTheme ? root.pageTheme.refresh : "#d4efff"; onClicked: nav.returnHome() }
            LabelText { color: root.pageTheme ? root.pageTheme.ink : "#101d42"; anchors.centerIn: parent; text: root.title; font.pixelSize: 12; font.weight: Font.Bold }
            WindowButton { shadowTone: root.pageTheme ? root.pageTheme.buttonShadow : "#3798bb"; anchors.verticalCenter: parent.verticalCenter; anchors.right: closeButton.left; anchors.rightMargin: 5; iconSource: assetBase+"ui/minimize.svg"; tone: root.pageTheme ? root.pageTheme.canvas : "#e9edf7"; onClicked: root.showMinimized() }
            WindowButton { id: closeButton; shadowTone: root.pageTheme ? root.pageTheme.buttonShadow : "#3798bb"; anchors.verticalCenter: parent.verticalCenter; anchors.right: parent.right; iconSource: assetBase+"ui/close.svg"; tone: root.pageTheme ? root.pageTheme.canvas : "#e9edf7"; onClicked: nav.close() }
        }
        Column {
            visible: root.page==="home"; x: 24; y: 72; width: parent.width-48; spacing: 17
            LabelText { text: "选择你的冒险助手"; font.pixelSize: 25 }
            HintText { text: "贴心辅助，把时间留给冒险。"; font.pixelSize: 13 }
            Repeater {
                model: [ {name:"一键上阵",desc:"粘贴阵容 · 一键配置队伍",icon:"lineup.svg",badge:"进入",tone:"#daf6b7",kind:"lineup"}, {name:"自动钓鱼",desc:"倍率 · 续饵 · 控鱼",icon:"rod-wood.png",badge:"进入",tone:"#d4efff",kind:"fishing"}, {name:"寻宝辅助",desc:"棋盘校正 · 宝藏概率 · 消耗估算",icon:"treasure.png",badge:"进入",tone:"#ddd5ff",kind:"treasure"}, {name:"漂流大赛",desc:"自动转盘 · 倍率 · 奖励优先级",icon:"rafting.png",badge:"进入",tone:"#bfeff1",kind:"rafting"} ]
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    width: parent.width; height: 113; radius: 17; color: entry.hovered ? "#fffdf0" : "#fffef5"; border.color: "#101d42"; border.width: 2.5; antialiasing: true
                    Behavior on color { ColorAnimation { duration: 140; easing.type: Easing.OutCubic } }
                    Rectangle { x: 18; anchors.verticalCenter: parent.verticalCenter; width: 74; height: 74; radius: 17; color: modelData.tone
                        Image { anchors.fill: parent; anchors.margins: 11; source: assetBase+"ui/"+modelData.icon; fillMode: Image.PreserveAspectFit; smooth: true; mipmap: true }
                    }
                    LabelText { x: 112; y: 26; text: modelData.name; font.pixelSize: 21 }
                    HintText { x: 112; y: 63; text: modelData.desc; font.pixelSize: 12 }
                    ActionButton { id: entry; objectName: "entry"+index; anchors.right: parent.right; anchors.rightMargin: 18; anchors.verticalCenter: parent.verticalCenter; width: 96; height: 40; tone: modelData.tone; text: modelData.badge
                        onClicked: { if(modelData.kind==="lineup")nav.openLineup();else if(modelData.kind==="fishing")nav.openFishing();else if(modelData.kind==="rafting")nav.openRafting();else nav.openTreasure() }
                    }
                }
            }
            HintText { text: "AutoTaTa · 每个功能均可独立启动"; font.pixelSize: 10 }
        }
        Loader {
            id: lineupPage; objectName: "lineupPageLoader"
            active: root.lineupLoaded; source: "LineupPage.qml"; visible: root.page==="lineup"
            x: 12; y: header.y+header.height+24; width: parent.width-24
            readonly property real naturalHeight: item ? item.naturalHeight : 820
            height: naturalHeight
        }
        Loader {
            id: raftingPage; objectName: "raftingPageLoader"
            active: root.raftingLoaded; source: "RaftingPage.qml"; visible: root.page==="rafting"
            x: 12; y: header.y+header.height+24; width: parent.width-24
            readonly property real naturalHeight: item ? item.naturalHeight : 820
            height: naturalHeight
        }
        Loader {
            id: treasurePage; objectName: "treasurePageLoader"
            active: root.treasureLoaded; source: "TreasurePage.qml"; visible: root.page==="treasure"
            x: 12; y: header.y+header.height+24; width: parent.width-24
            // The page supplies its complete natural height, including optional sections.
            readonly property real naturalHeight: item ? item.implicitHeight : 542
            height: naturalHeight
        }
        AppDialog {
            id: notice; objectName: "noticeDialog"; uiScale: root.visualZoom; parent: root.contentItem
            property alias text: notice.message
        }

    }
    // Keep the resize target in window pixels, accessible even at the smallest scale.
    Item {
        objectName: "resizeGrip"; visible: root.page!=="home"
        width: 24; height: 24
        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 3
        opacity: resizeArea.containsMouse || root.resizing ? .85 : .45
        Behavior on opacity { NumberAnimation { duration: 130; easing.type: Easing.OutCubic } }
        Image { objectName: "resizeGripIcon"; anchors.fill: parent; source: assetBase+"ui/resize-grip.svg"; smooth: true }
        MouseArea {
            id: resizeArea; objectName: "treasureResizeArea"
            anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.SizeFDiagCursor
            property point origin
            property real initialZoom: 1
            property real initialHeight: 1
            property bool dragging: false
            onPressed: function(mouse) {
                dragging=true; root.resizing=true
                origin=mapToGlobal(mouse.x,mouse.y)
                initialZoom=root.visualZoom; initialHeight=root.baseHeight
            }
            onPositionChanged: function(mouse) {
                if (!dragging) return
                let now=mapToGlobal(mouse.x,mouse.y)
                let dx=(now.x-origin.x)/root.baseWidth
                let dy=(now.y-origin.y)/initialHeight
                let delta=Math.abs(dx)>=Math.abs(dy) ? dx : dy
                root.treasureZoom=Math.max(root.minZoom,Math.min(root.maxZoom,initialZoom+delta))
            }
            onReleased: { dragging=false; root.resizing=false }
            onCanceled: { dragging=false; root.resizing=false }
        }
    }
    Connections { target: nav; function onMessage(message) { notice.text=message;notice.open() } }
}
