import QtQuick
import QtQuick.Controls.Basic
Column {
    id: page
    property var s: rafting.state
    property real uiScale: 1
    spacing: 14
    readonly property real naturalHeight: implicitHeight
    Rectangle {
        width: parent.width; height: connection.implicitHeight+32
        radius: 16; color: "#fffef5"; border.color: "#101d42"; border.width: 2
        Column {
            id: connection; x: 16; y: 16; width: parent.width-32; spacing: 10
            Row {
                spacing: 10; width: parent.width
                LabelText { text: "操作模式"; width: 84; anchors.verticalCenter: parent.verticalCenter }
                Picker { objectName: "raftingModePicker"; width: connection.width-94; model: ["后台 MuMuSDK", "前台 Maa", "通用后台 ADB + MaaTouch"]; currentIndex: page.s.modeIndex; enabled: !page.s.running; onActivated: rafting.setMode(currentIndex) }
            }
            Row {
                spacing: 10; width: parent.width
                LabelText { text: "游戏设备"; width: 84; anchors.verticalCenter: parent.verticalCenter }
                Picker { objectName: "raftingDevicePicker"; width: connection.width-164; model: page.s.devices; currentIndex: page.s.deviceIndex; displayText: currentIndex>=0 ? currentText : "请选择设备"; enabled: !page.s.running; onActivated: rafting.selectDevice(currentIndex) }
                ActionButton { width: 60; text: page.s.refreshing ? "查找中" : "刷新"; tone: "#d4efff"; enabled: !page.s.running && !page.s.refreshing; onClicked: rafting.refresh() }
            }
            Field { visible: page.s.modeIndex===2; width: parent.width; placeholderText: "也可输入 ADB 地址，例如 127.0.0.1:16384"; enabled: !page.s.running; onEditingFinished: { if(text.length)rafting.setAddress(text) } }
            Row {
                spacing: 10
                HintText { text: "画面边距"; width: 84; anchors.verticalCenter: parent.verticalCenter }
                HintText { text: "顶部"; anchors.verticalCenter: parent.verticalCenter }
                Field { width: 66; text: String(page.s.crop_top); enabled: !page.s.running; onEditingFinished: rafting.setValue("crop_top",text) }
                HintText { text: "底部"; anchors.verticalCenter: parent.verticalCenter }
                Field { width: 66; text: String(page.s.crop_bottom); enabled: !page.s.running; onEditingFinished: rafting.setValue("crop_bottom",text) }
                HintText { text: "0 = 自动识别"; anchors.verticalCenter: parent.verticalCenter }
            }
        }
    }
    Rectangle {
        width: parent.width; height: multiplierColumn.implicitHeight+32
        radius: 16; color: "#fffef5"; border.color: "#101d42"; border.width: 2
        Column {
            id: multiplierColumn; x: 16; y: 16; width: parent.width-32; spacing: 12
            LabelText { text: "期望倍率"; font.pixelSize: 15 }
            Row {
                spacing: 9
                Repeater {
                    model: page.s.multipliers
                    ActionButton {
                        required property int modelData
                        objectName: "raftingMultiplier"+modelData
                        width: (multiplierColumn.width-9*(page.s.multipliers.length-1))/page.s.multipliers.length; height: 36; text: "x"+modelData
                        tone: page.s.desired_multiplier===modelData ? "#ffd65a" : "#d4efff"
                        onClicked: rafting.setValue("desired_multiplier",modelData)
                    }
                }
            }
            HintText { text: "随时修改，下次转盘前生效；达到可用上限时使用最大倍率。"; font.pixelSize: 11 }
            Row {
                spacing: 14
                LabelText { text: "漂流预算"; width: 96; anchors.verticalCenter: parent.verticalCenter }
                Field { objectName: "raftingBudget"; width: 100; text: String(page.s.boat_budget); validator: IntValidator { bottom: 0; top: 99999999 } onEditingFinished: rafting.setValue("boat_budget",text) }
                HintText { text: "艘 · 0 = 不限"; anchors.verticalCenter: parent.verticalCenter }
            }
            Row {
                spacing: 20
                LabelText { text: "当前倍率 "+(page.s.currentMultiplier ? "x"+page.s.currentMultiplier : "—")+(page.s.maximum ? " · 最大" : ""); font.pixelSize: 12 }
                LabelText { text: "剩余船 "+(page.s.stock===null || page.s.stock===undefined ? "—" : page.s.stock); font.pixelSize: 12 }
            }
        }
    }
    Rectangle {
        width: parent.width; height: priorityColumn.implicitHeight+32
        radius: 16; color: "#fffef5"; border.color: "#101d42"; border.width: 2
        Column {
            id: priorityColumn; x: 16; y: 16; width: parent.width-32; spacing: 12
            Row {
                width: parent.width
                LabelText { text: "奖励优先级"; font.pixelSize: 15; width: parent.width-144; anchors.verticalCenter: parent.verticalCenter }
                ActionButton { objectName: "restoreRecommended"; width: 144; height: 30; text: "恢复推荐排序"; tone: "#d4efff"; onClicked: rafting.restoreRecommended() }
            }
            HintText { text: "左右拖拽，越靠左越优先；下一次三选一时生效。"; font.pixelSize: 11 }
            Row {
                id: priorityRows; width: parent.width; spacing: 10
                readonly property real stepWidth: (width+spacing)/6
                Repeater {
                    model: page.s.rewards
                    delegate: Item {
                        id: priorityItem
                        required property int index
                        required property var modelData
                        objectName: "rewardRow"+index
                        width: priorityRows.stepWidth-priorityRows.spacing; height: 92; z: dragger.pressed ? 10 : 0
                        Rectangle {
                            id: tile; width: parent.width; height: parent.height; radius: 12
                            color: dragger.pressed ? "#ffd65a" : "#eff8ff"; border.color: "#8496b4"; border.width: 1
                            Image { x: 6; y: 13; width: parent.width-12; height: 66; source: assetBase+"ui/rewards/"+priorityItem.modelData.key+".png"; fillMode: Image.PreserveAspectFit; smooth: true; mipmap: true }
                            MouseArea {
                                id: dragger; objectName: "rewardDrag"+priorityItem.index
                                anchors.fill: parent; hoverEnabled: true; cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                                drag.target: tile; drag.axis: Drag.XAxis
                                drag.minimumX: -priorityItem.index*priorityRows.stepWidth
                                drag.maximumX: (5-priorityItem.index)*priorityRows.stepWidth
                                onReleased: { let source=priorityItem.index; let target=Math.max(0,Math.min(5,source+Math.round(tile.x/priorityRows.stepWidth)));tile.x=0;rafting.moveReward(source,target) }
                                onCanceled: tile.x=0
                            }
                            HelpTip { text: priorityItem.modelData.name; visible: dragger.containsMouse && !dragger.pressed }
                        }
                    }
                }
            }
        }
    }
    Row {
        width: parent.width; spacing: 16
        ActionButton { objectName: "raftingStart"; width: (page.width-16)/2; large: true; centeredLabel: true; text: "开始漂流"; shortcut: "Home"; tone: "#5bdfe4"; enabled: !page.s.running && !page.s.refreshing && !page.s.shutdownPending; onClicked: rafting.start() }
        ActionButton { objectName: "raftingStop"; width: (page.width-16)/2; large: true; centeredLabel: true; text: "停止"; shortcut: "PgDown"; tone: "#ffaaa0"; enabled: page.s.running; onClicked: rafting.stop() }
    }
    Rectangle {
        width: parent.width; height: statusColumn.implicitHeight+24; radius: 12; color: "#d4efff"
        Column {
            id: statusColumn; x: 12; y: 12; width: parent.width-24; spacing: 6
            LabelText { width: parent.width; text: page.s.status; wrapMode: Text.WordWrap; font.pixelSize: 12 }
            HintText { text: "本次完成 "+page.s.rounds+" 轮 · 已提交用船 "+page.s.used+" / "+(Number(page.s.boat_budget)||"不限"); font.pixelSize: 11 }
        }
    }
    Rectangle {
        width: parent.width; height: shutdownColumn.implicitHeight+32
        radius: 16; color: "#fffef5"; border.color: "#101d42"; border.width: 2
        Column {
            id: shutdownColumn; x: 16; y: 16; width: parent.width-32; spacing: 10
            Row {
                width: parent.width; spacing: 30
                Row {
                    spacing: 10
                    LabelText { text: "完成后关机"; anchors.verticalCenter: parent.verticalCenter }
                    BaitSwitch { objectName: "raftingShutdown"; checked: page.s.shutdown_on_stop; helpText: "正常自动完成后关机，手动停止不关机"; onToggled: rafting.setValue("shutdown_on_stop",checked) }
                }
                Row {
                    spacing: 10
                    LabelText { text: "强制关机"; anchors.verticalCenter: parent.verticalCenter }
                    BaitSwitch { objectName: "raftingForceShutdown"; checked: page.s.shutdown_force; helpText: "强制关机，未保存内容会丢失"; onToggled: rafting.setValue("shutdown_force",checked) }
                }
            }
            Row {
                spacing: 10; width: parent.width
                HintText { width: parent.width-(page.s.shutdownPending ? 76 : 0); text: page.s.shutdownStatus || "仅正常自动完成时关机；强制关机会关闭未保存的应用。"; font.pixelSize: 11; elide: Text.ElideRight; color: page.s.shutdownPending ? "#d12e35" : "#597499" }
                ActionButton { objectName: "raftingCancelShutdown"; visible: page.s.shutdownPending; width: 66; height: 25; text: "取消"; onClicked: rafting.cancelShutdown() }
            }
        }
    }
}
