import QtQuick
Card {
    width: 591; height: 212
    title: "鱼饵设置"; icon: assetBase+"ui/bait-icon.png"
    Column {
        width: parent.width; spacing: 8
        Row {
            width: parent.width; height: 48; spacing: 24
            Item {
                width: 44; height: 44
                Rectangle {
                    x: 2.75; y: 2.75; width: 38.5; height: 38.5; radius: 5
                    color: ["#dde5ec","#a1a8bd","#a16de3","#f2b826","#ed5c61"][backend.state.rodLevel || 0]
                    border.color: "#101d42"; border.width: .825; antialiasing: true
                }
                Image {
                    objectName: "rodLevelIcon"
                    x: 2.75; y: 2.75; width: 38.5; height: 37.125
                    visible: backend.state.rodLevel>0
                    source: backend.state.rodLevel>0 ? assetBase+"ui/rod-"+["","wood","purple","gold","red"][backend.state.rodLevel]+".png" : ""
                    fillMode: Image.PreserveAspectFit; smooth: true; mipmap: true; sourceSize: Qt.size(96,96)
                }
                LabelText { anchors.centerIn: parent; text: "?"; visible: !backend.state.rodLevel; color: "#597499"; font.pixelSize: 20 }
            }
            Column {
                width: 182; spacing: 2; anchors.verticalCenter: parent.verticalCenter
                LabelText { helpText: "鱼竿自带的基础幸运值"; height: 18; text: backend.state.rodLevel ? "基础幸运值 "+backend.state.rodLevel : "基础幸运值待识别" }
                HintText { height: 15; text: "抛竿前自动识别"; font.pixelSize: 10 }
            }
            Column {
                width: 250; spacing: 2; anchors.verticalCenter: parent.verticalCenter
                LabelText { objectName: "luckText"; helpText: "当前幸运值与满饵目标"; height: 18; text: backend.state.luckText; color: backend.state.luckFull ? "#36931b" : "#597499" }
                HintText { height: 15; text: "满饵目标 = 鱼竿等级 + 4"; font.pixelSize: 10 }
            }
        }
        Row {
            width: parent.width; height: 28; spacing: 24
            Row {
                width: 250; height: 28; spacing: 12
                LabelText { width: 160; anchors.verticalCenter: parent.verticalCenter; text: "自动续饵" }
                BaitSwitch { objectName: "autoBaitSwitch"; helpText: "有鱼饵且未满饵时自动续饵"; checked: backend.state.auto_bait; enabled: !backend.state.closing; onToggled: backend.setValue("auto_bait",checked) }
            }
            Row {
                width: 250; height: 28; spacing: 53
                LabelText { width: 84; anchors.verticalCenter: parent.verticalCenter; text: "本次用饵预算" }
                Row {
                    spacing: 8; height: 28
                    Field { objectName: "baitLimitField"; helpText: "本机用饵上限，0不限"; width: 62; anchors.verticalCenter: parent.verticalCenter; text: backend.state.bait_limit; enabled: !backend.state.closing; validator: IntValidator { bottom: 0; top: 99999 } onTextEdited: backend.draftValue("bait_limit",text); onEditingFinished: backend.setValue("bait_limit",text) }
                    HintText { anchors.verticalCenter: parent.verticalCenter; text: "0 = 不限"; font.pixelSize: 10 }
                }
            }
        }
        Image { width: 533; height: 4; source: assetBase+"ui/bait-divider.svg"; smooth: true }
        Row {
            width: parent.width; height: 28; spacing: 24
            Row {
                width: 250; height: 28; spacing: 12
                LabelText { width: 160; anchors.verticalCenter: parent.verticalCenter; text: "满幸运值保护" }
                BaitSwitch { objectName: "fullBaitProtectionSwitch"; helpText: "鱼饵够补满才投放"; checked: backend.state.full_bait_protection; enabled: !backend.state.closing; onToggled: backend.setValue("full_bait_protection",checked) }
            }
            Row {
                width: 250; height: 28; spacing: 12
                LabelText { width: 160; anchors.verticalCenter: parent.verticalCenter; text: "无法维持满饵时停止" }
                BaitSwitch { objectName: "stopBaitSwitch"; helpText: "补不满则钓至增益结束"; checked: backend.state.stop_on_bait_end; enabled: !backend.state.closing; onToggled: backend.setValue("stop_on_bait_end",checked) }
            }
        }
        Row {
            width: parent.width; height: 16; spacing: 24
            HintText { width: 250; text: "本机持有鱼饵不满足满饵要求，不打窝"; font.pixelSize: 10 }
            HintText { width: 250; text: "不足以补满时停止续饵，钓到当前增益全部结束"; font.pixelSize: 10 }
        }
    }
}
