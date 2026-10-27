import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Window
Window {
    id: window
    property bool embedded: false
    signal backRequested()
    objectName: "mainWindow"
    visible: !animateStartup
    title: "TaTaAutoFish by maozo"
    flags: Qt.Window | Qt.FramelessWindowHint
    color: "#8eeaf3"
    property real entranceScale: 1
    function reveal() {
        opacity=0
        entranceScale=.97
        visible=true
        entrance.restart()
    }
    ParallelAnimation {
        id: entrance
        NumberAnimation { target: window; property: "opacity"; to: 1; duration: 480; easing.type: Easing.OutCubic }
        NumberAnimation { target: window; property: "entranceScale"; to: 1; duration: 580; easing.type: Easing.OutCubic }
    }
    Binding { target: window.contentItem; property: "scale"; value: window.entranceScale }
    Binding { target: window.contentItem; property: "transformOrigin"; value: Item.Center }
    property bool resizing: false
    property bool modeMenuVisible: modePicker.popup.visible
    property real modeMenuScale: modePicker.popup.uiScale
    property real maxZoom: Math.min(2, (Screen.desktopAvailableWidth-20)/baseWidth, (Screen.desktopAvailableHeight-40)/baseHeight)
    property real zoom: Math.max(.5,Math.min(maxZoom,backend.state.ui_scale))
    property real visualZoom: zoom
    property int baseWidth: 615
    property int baseHeight: 881
    property real availableHeight: Math.max(250, Screen.desktopAvailableHeight-40)
    width: Math.round(baseWidth*visualZoom)
    height: Math.round(Math.min(baseHeight*visualZoom,availableHeight))
    Behavior on visualZoom { enabled: !window.resizing; NumberAnimation { duration: 160; easing.type: Easing.InOutCubic } }
    onZoomChanged: {
        x=Math.max(0,Math.min(x,Screen.desktopAvailableWidth-baseWidth*zoom))
        y=Math.max(0,Math.min(y,Screen.desktopAvailableHeight-Math.min(baseHeight*zoom,availableHeight)))
    }
    onClosing: function(event) {
        if (!backend.state.canClose) { event.accepted=false; backend.closeRequested() }
    }
    Rectangle { anchors.fill: parent; color: "#8eeaf3"; radius: 15*window.visualZoom; antialiasing: true }
    Item {
        id: scene
        objectName: "scaledScene"
        width: window.baseWidth; height: window.height/window.visualZoom
        scale: window.visualZoom; transformOrigin: Item.TopLeft
        Item {
            id: titlebar
            x: 12; y: 3; width: 591; height: 39
            MouseArea { anchors.fill: parent; onPressed: window.startSystemMove() }
            ActionButton { objectName: "backHome"; visible: window.embedded; x: 0; y: 1; width: 82; height: 36; text: "返回"; tone: "#d4efff"; onClicked: window.backRequested() }
            HintText { anchors.centerIn: parent; text: "TaTaAutoFish by maozo"; font.pixelSize: 12; font.weight: Font.Bold }
            WindowButton { x: 530; iconSource: assetBase+"ui/minimize.svg"; leftPadding: 4; rightPadding: 8; tone: "#8eeaf3"; onClicked: window.showMinimized() }
            WindowButton { x: 562; iconSource: assetBase+"ui/close.svg"; leftPadding: 4; rightPadding: 8; tone: "#8eeaf3"; onClicked: backend.closeRequested() }
        }
        Flickable {
            id: viewport
            objectName: "settingsViewport"
            x: 12; y: 50; width: 591
            height: Math.max(100,scene.height-50-footer.height-10)
            contentHeight: panels.height; clip: true
            boundsBehavior: Flickable.StopAtBounds
            interactive: contentHeight>height
            ScrollBar.vertical: ScrollBar { policy: viewport.contentHeight>viewport.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
            Column {
                id: panels
                width: viewport.width; spacing: 9
                Card {
                    width: parent.width; height: 96; title: "设备设置"; icon: assetBase+"ui/device.svg"
                    LabelText { x: 0; y: 6; text: "目标设备" }
                    Picker {
                        id: devices
                        objectName: "devicePicker"; helpText: "选择运行游戏的设备"
                        x: 72; y: 0; width: 374
                        model: backend.state.devices; currentIndex: backend.state.deviceIndex
                        displayText: backend.state.deviceText
                        editable: backend.state.mode==="maatouch"
                        enabled: !backend.state.closing && !backend.state.refreshing
                        onActivated: backend.selectDevice(currentIndex)
                        onAccepted: backend.setAddress(editText)
                        contentItem: TextInput {
                            text: devices.editable ? devices.editText : devices.displayText
                            font: devices.font; color: "#101d42"; verticalAlignment: Text.AlignVCenter
                            readOnly: !devices.editable; selectByMouse: devices.editable
                            enabled: devices.editable; clip: true
                            renderType: Text.QtRendering
                            
                        }
                    }
                    ActionButton { x: 457; y: 0; width: 96; text: backend.state.refreshing ? "发现中…" : "刷新"; iconSource: backend.state.refreshing ? "" : assetBase+"ui/refresh.svg"; tone: "#d4efff"; enabled: !backend.state.closing && !backend.state.refreshing; onClicked: backend.refresh() }
                    HintText { x: 72; y: 38; width: 481; text: backend.state.requirement; font.pixelSize: 10; elide: Text.ElideRight }
                }
                Card {
                    width: parent.width; height: 138; title: "钓鱼设置"; accent: "#ffd442"; icon: assetBase+"ui/gear.svg"
                    LabelText { x: 0; y: 6; text: "期望倍率" }
                    Picker {
                        objectName: "multiplierPicker"; helpText: "每竿消耗的钓竿倍数"
                        x: 72; y: 0; width: 160; model: [1,2,3,5,10,20,50,100]
                        currentIndex: model.indexOf(backend.state.desired_multiplier)
                        onActivated: backend.setValue("desired_multiplier",model[currentIndex])
                    }
                    LabelText { x: 274; y: 6; text: "本次用竿预算" }
                    Field { objectName: "budgetField"; helpText: "本次用竿上限，0不限"; x: 366; y: 0; width: 74; text: backend.state.rod_budget; enabled: !backend.state.closing; validator: IntValidator { bottom: 0; top: 99999999 } onTextEdited: backend.draftValue("rod_budget",text); onEditingFinished: backend.setValue("rod_budget",text) }
                    HintText { x: 452; y: 7; text: "0 = 不限"; font.pixelSize: 10 }
                    HintText { x: 0; y: 33; text: "倍率修改下一竿生效，不足时用可用最大值；超预算停止。"; font.pixelSize: 10 }
                    LabelText { x: 0; y: 60; text: "操作模式" }
                    Picker {
                        id: modePicker
                        objectName: "modePicker"; helpText: "选择前台或后台操作方式"
                        x: 72; y: 54; width: 481
                        model: ["后台 MuMuSDK","前台 Maa","通用兼容后台 ADB + MaaTouch"]
                        currentIndex: backend.state.modeIndex; enabled: !backend.state.closing
                        onActivated: backend.setMode(currentIndex)
                    }
                }
                BaitPanel { width: parent.width }
                Card {
                    width: parent.width; height: 96; title: "画面裁剪"; accent: "#bcadf5"; icon: assetBase+"ui/crop.svg"
                    LabelText { x: 0; y: 7; text: "上边距" }
                    Field { objectName: "cropTopField"; helpText: "顶部裁剪像素，0自动"; x: 72; y: 0; width: 191; text: backend.state.crop_top; enabled: !backend.state.closing; validator: IntValidator { bottom: 0; top: 99999 } onTextEdited: backend.draftValue("crop_top",text); onEditingFinished: backend.setValue("crop_top",text) }
                    LabelText { x: 278; y: 7; text: "下边距" }
                    Field { objectName: "cropBottomField"; helpText: "底部裁剪像素，0自动"; x: 366; y: 0; width: 187; text: backend.state.crop_bottom; enabled: !backend.state.closing; validator: IntValidator { bottom: 0; top: 99999 } onTextEdited: backend.draftValue("crop_bottom",text); onEditingFinished: backend.setValue("crop_bottom",text) }
                    HintText { x: 0; y: 33; text: "均为 0 时自动识别；手动边距单位：像素，仅影响识别画面。"; font.pixelSize: 10 }
                }
                Item {
                    width: parent.width; height: 52
                    ActionButton { id: start; objectName: "startButton"; width: 326; large: true; text: "开始钓鱼"; shortcut: "Home"; tone: "#7de728"; iconSource: assetBase+"ui/rod-wood.png"; enabled: !backend.state.running && !backend.state.refreshing && !backend.state.closing; onClicked: backend.start() }
                    ActionButton { id: stop; objectName: "stopButton"; x: 337; width: 254; large: true; text: "停止"; iconSource: assetBase+"ui/stop.svg"; shortcut: "PgDown"; onClicked: backend.stop() }
                }
            }
        }
        Item {
            id: footer
            x: 12; y: scene.height-height-9; width: 591; height: 180
            Card {
                x: 0; width: parent.width; height: parent.height
                LabelText { x: 0; y: 3; text: "● 状态"; color: "#36931b"; font.pixelSize: 11 }
                LabelText { x: 222; y: 3; text: "已完成 "+backend.state.catchCount+" 次"; font.pixelSize: 11 }
                LabelText { x: 341; y: 3; text: "已用钓竿 "+backend.state.rodsUsed+" / "+(Number(backend.state.rod_budget)||"不限"); font.pixelSize: 11 }
                Rectangle {
                    x: 0; y: 27; width: parent.width; height: 32; radius: 6; color: "#edf7ff"; antialiasing: true
                    HintText { objectName: "baitStatusText"; x: 10; width: 320; height: parent.height; text: backend.state.baitDisplay; font.weight: Font.Bold; font.pixelSize: 10; elide: Text.ElideRight }
                    HintText { x: 342; width: 190; height: parent.height; text: "本机已用 "+backend.state.baitUsed+" / "+(Number(backend.state.bait_limit)||"不限"); font.weight: Font.Bold; font.pixelSize: 10 }
                }
                HintText { objectName: "statusText"; helpText: "当前钓鱼进度与状态"; x: 0; y: 66; width: parent.width; height: 21; text: backend.state.status; elide: Text.ElideRight; font.pixelSize: 10 }
                Rectangle { x: 0; y: 88; width: parent.width; height: 1; color: "#d1e0ed" }
                Row {
                    x: 0; y: 96; spacing: 40; height: 28
                    Row {
                        spacing: 12; height: 28
                        LabelText { text: "停止钓鱼后关机"; anchors.verticalCenter: parent.verticalCenter }
                        BaitSwitch { objectName: "shutdownSwitch"; helpText: "自动停钓后关机，手动停止不关机"; checked: backend.state.shutdown_on_stop; onToggled: backend.setValue("shutdown_on_stop",checked) }
                    }
                    Row {
                        spacing: 18; height: 28
                        LabelText { text: "强制关机"; anchors.verticalCenter: parent.verticalCenter }
                        BaitSwitch { objectName: "forceShutdownSwitch"; helpText: "强制关机，未保存内容会丢失"; checked: backend.state.shutdown_force; onToggled: backend.setValue("shutdown_force",checked) }
                    }
                }
                HintText { x: 0; y: 131; width: parent.width-(backend.state.shutdownPending ? 76 : 0); height: 22; color: backend.state.shutdownPending ? "#d12e35" : "#597499"; text: backend.state.shutdownStatus || "仅正常自动停止时关机；强制关机会关闭未保存的应用。"; font.pixelSize: 10; elide: Text.ElideRight }
                ActionButton { objectName: "cancelShutdownButton"; x: parent.width-66; y: 129; width: 66; height: 25; text: "取消"; visible: backend.state.shutdownPending; onClicked: backend.cancelShutdown() }
            }

        }
    }
    Item {
        id: grip
        objectName: "resizeGrip"
        width: 24; height: 24
        anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.margins: 3
        opacity: resizeArea.containsMouse || window.resizing ? .85 : .45
        Behavior on opacity { NumberAnimation { duration: 130; easing.type: Easing.OutCubic } }
        Image { objectName: "resizeGripIcon"; anchors.fill: parent; source: assetBase+"ui/resize-grip.svg"; smooth: true }
        MouseArea {
            id: resizeArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.SizeFDiagCursor
            property point origin
            property real initialZoom: 1
            property bool dragging: false
            onPressed: function(mouse) {
                dragging=true; window.resizing=true
                origin=mapToGlobal(mouse.x,mouse.y); initialZoom=window.visualZoom
            }
            onPositionChanged: function(mouse) {
                if (!dragging)return
                let now=mapToGlobal(mouse.x,mouse.y)
                let dx=(now.x-origin.x)/window.baseWidth
                let dy=(now.y-origin.y)/window.baseHeight
                let delta=Math.abs(dx)>=Math.abs(dy) ? dx : dy
                backend.resizeTo(Math.max(.5,Math.min(window.maxZoom,initialZoom+delta)))
            }
            onReleased: { dragging=false; window.resizing=false; backend.finishResize() }
            onCanceled: { dragging=false; window.resizing=false; backend.finishResize() }
        }
    }
    AppDialog {
        id: warningDialog; objectName: "warningDialog"; parent: window.contentItem
        uiScale: window.visualZoom
        onAccepted: backend.confirmStart()
    }

    Connections {
        target: backend
        function onWarning(title,message) { warningDialog.title=title; warningDialog.message=message; warningDialog.open() }
        function onPulse(name) { if(name==="start")start.pulse();else stop.pulse() }
    }
}
