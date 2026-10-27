import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
Item {
    id: page; objectName: "treasurePage"
    implicitHeight: 811
    property int selectedCell: -1
    property real popupLeft: 0
    property real popupTop: 0
    property int editingIndex: -1
    property string editError: ""
    readonly property var snapshot: treasure.state
    readonly property bool statusWarning: snapshot.recognitionStatus.label==="待校正" || snapshot.recognitionStatus.label==="连接异常"
    readonly property bool calculationError: ["失败","无效","没有符合","暂未采到"].some(word=>snapshot.status.indexOf(word)>=0)
    readonly property int occupied: snapshot.shapes.reduce((n,s)=>n+s[0]*s[1]*s[2],0)
    readonly property real zoom: page.Window.window ? page.Window.window.visualZoom : 1
    readonly property var eligible: snapshot.probabilities.filter((p,i)=>snapshot.cells[i]===0 && (snapshot.markedTreasure||[]).indexOf(i)<0)
    readonly property real maximum: eligible.length ? Math.max.apply(null,eligible) : 0
    readonly property real minimum: eligible.length ? Math.min.apply(null,eligible) : 0
    readonly property string consumptionPrimary: snapshot.busy ? "计算中…" : snapshot.estimatePrimary
    readonly property var consumptionMatch: consumptionPrimary.match(/^(约|还需)\s*([\d.]+)\s*镐子$/)
    readonly property string consumptionGrid: snapshot.busy || calculationError || !snapshot.estimateDetails ? "" : snapshot.estimateDetails.split("；")[0].replace(/^\s*\/\s*/, "").trim()
    readonly property string consumptionReference: snapshot.busy || calculationError ? "" : (snapshot.estimateDetails.split("；")[1] || "").trim()
    readonly property string consumptionNote: snapshot.allLocated || snapshot.allIdentified ? "按剩余宝物占格计算，请核对推断。" : "近似估算，不含队友帮助。"
    CampTheme { id: camp }
    function cellColor(chance) {
        if(chance==null) return camp.white
        if(chance>=maximum-0.0000001 && maximum>0) return "#ffce66"
        let t=maximum>minimum ? (chance-minimum)/(maximum-minimum) : 0
        if(t>.75)return "#fee891"
        if(t>.25)return "#feeec4"
        return "#f5f4ef"
    }
    function openEditor(index) {
        editingIndex=index; editError=""
        let s=index<0 ? [1,1,1] : snapshot.shapes[index]
        widthInput.text=s[0];heightInput.text=s[1];quantityInput.text=s[2]
        treasureDialog.open()
    }
    function openCell(index,node) {
        selectedCell=index
        let pt=node.mapToItem(page,node.width/2,node.height)
        popupLeft=Math.max(3,Math.min(page.width-cellPopup.width-3,pt.x-cellPopup.width/2))
        popupTop=pt.y+6
        cellPopup.open()
    }
    Column {
        width: page.width; spacing: 14
        Card {
            objectName: "recognitionCard"; width: parent.width; height: 123
            title: "设备设置"; icon: assetBase+"ui/device.svg"; accent: camp.blue; colorTheme: camp
            Row { width: parent.width; height: 38; spacing: 10
                Picker { objectName: "treasureDevicePicker"; colorTheme: camp; anchors.verticalCenter: parent.verticalCenter; width: 360; height: 30; model: snapshot.live.devices; currentIndex: snapshot.live.deviceIndex; enabled: !snapshot.live.running; displayText: count ? currentText : "请选择 MuMu 窗口"; onActivated: treasure.chooseDevice(currentIndex) }
                ActionButton { colorTheme: camp; anchors.verticalCenter: parent.verticalCenter; width: 70; text: "刷新"; iconSource: assetBase+"ui/refresh.svg"; enabled: !snapshot.live.running; onClicked: treasure.refreshDevices() }
                Item { width: 129; height: 29; anchors.verticalCenter: parent.verticalCenter
                    LabelText { x: 8; text: "覆盖层"; height: 29 }
                    BaitSwitch { x: 52; objectName: "overlaySwitch"; checked: snapshot.live.overlay; helpText: "在模拟器上显示概率"; onToggled: treasure.setOverlay(checked) }
                }
                ActionButton { objectName: "recognitionButton"; width: 150; height: 38; anchors.verticalCenter: parent.verticalCenter
                    colorTheme: camp; tone: snapshot.live.running ? "#ffd9cf" : camp.yellow
                    text: snapshot.live.running ? "停止识别" : "自动识别"
                    onClicked: snapshot.live.running ? treasure.stopWatch() : treasure.startWatch()
                }
            }
            Rectangle { objectName: "recognitionStatusRow"; y: 45; width: parent.width; height: 30; radius: 6
                color: page.statusWarning ? camp.warningSurface : "transparent"
                border.color: page.statusWarning ? "#ac2b20" : "transparent"; border.width: 0
                Row { anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8; spacing: 8
                    Rectangle { width: 10; height: 10; radius: 5; anchors.verticalCenter: parent.verticalCenter; color: page.statusWarning ? "#ffffff" : snapshot.recognitionStatus.color }
                    LabelText { height: 30; text: snapshot.recognitionStatus.label; color: page.statusWarning ? "#ffffff" : snapshot.recognitionStatus.color; font.pixelSize: 14; font.weight: Font.Black }
                    HintText { height: 30; text: "—"; color: page.statusWarning ? "#ffffff" : camp.secondary; font.pixelSize: 14; font.weight: Font.Bold }
                    HintText { objectName: "recognitionStatusDetail"; height: 30; width: parent.width-115; text: snapshot.recognitionStatus.detail; helpText: text; color: page.statusWarning ? "#ffffff" : "#597499"; elide: Text.ElideRight; font.pixelSize: 13; font.weight: Font.Black }
                }
            }
        }
        Row { width: parent.width; height: 674; spacing: 10
            Card {
                objectName: "boardCard"; width: 482; height: 674; colorTheme: camp; panelTop: 0; titleTop: -5; panelRightInset: 2
                WarningBadge { objectName: "boardWarningBadge"; x: grid.x+440-width; y: -18; detail: snapshot.boardWarning || "" }
                title: "棋盘校正"; icon: assetBase+"ui/treasure-edit.svg"; accent: camp.purple
                    Row { x: 4; y: 20; height: 54; spacing: 43
                        Column { width: 94; spacing: 6
                            LabelText { text: "棋盘"; height: 18 }
                            Row { spacing: 6
                                Field { id: sizeInput; objectName: "sizeInput"; colorTheme: camp; width: 52; height: 30; text: snapshot.size; validator: IntValidator { bottom: 3; top: 9 } onEditingFinished: { if(Number(text)!==snapshot.size)sizeDialog.open() } }
                                LabelText { height: 30; text: "× "+snapshot.size }
                            }
                        }
                        Column { width: 80; spacing: 6
                            LabelText { text: "每格消耗"; height: 18 }
                            Field { objectName: "costInput"; colorTheme: camp; width: 80; height: 30; text: snapshot.cost; validator: IntValidator { bottom: 1; top: 9999 } onEditingFinished: { if(!treasure.editBoard(snapshot.size,Number(text)))text=snapshot.cost } }
                        }
                    }
                Row { x: 264; y: 45; spacing: 10
                    ActionButton { objectName: "undoMarksButton"; width: 80; text: "撤销"; colorTheme: camp; enabled: snapshot.canUndo; onClicked: treasure.undo() }
                    ActionButton { objectName: "clearMarksButton"; width: 90; text: "清空标记"; colorTheme: camp; onClicked: clearDialog.open() }
                }
                LabelText { x: 4; y: 534; width: 440; height: 29; font.pixelSize: 15; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight; text: snapshot.allLocated ? "宝物已全部定位，等待挖完" : snapshot.allIdentified ? "宝物均已认出，位置仍待验证" : "待找出："+(snapshot.pendingShapes || snapshot.shapes).map(s=>s[0]+" × "+s[1]+"（"+s[2]+" 件剩余）").join("、"); helpText: text }
                Grid { id: grid; x: 4; y: 86; columns: snapshot.size; columnSpacing: 4; rowSpacing: 4
                    Repeater { model: snapshot.cells
                        delegate: Rectangle {
                            required property int index; required property int modelData
                            objectName: "treasureCell"+index
                            property bool marked: modelData===2 || (snapshot.markedTreasure||[]).indexOf(index)>=0
                            property bool predicted: modelData===0 && (snapshot.certainTreasure||[]).indexOf(index)<0 && (snapshot.predictedTreasure||[]).indexOf(index)>=0
                            property var chance: snapshot.probabilities.length>index ? snapshot.probabilities[index] : null
                            property bool recommended: (snapshot.recommendedCells||[]).indexOf(index)>=0
                            width: (440-(snapshot.size-1)*4)/snapshot.size; height: width; radius: 6; antialiasing: true
                            color: modelData===1 ? camp.emptyCell : marked ? camp.yellow : page.cellColor(chance)
                            border.width: page.selectedCell===index && cellPopup.visible ? 2 : 1
                            border.color: page.selectedCell===index && cellPopup.visible ? "#946de0" : camp.border
                            LabelText { anchors.centerIn: parent; visible: !parent.marked && (!(snapshot.allLocated || snapshot.allIdentified) || modelData===1); text: modelData===1 ? "空" : chance==null ? "·" : Math.round(chance*100)+"%"; color: modelData===1 ? camp.white : camp.ink }
                            Image { anchors.centerIn: parent; width: Math.min(30,parent.width*.5); height: width; visible: parent.marked; source: assetBase+"ui/treasure-chest.svg"; fillMode: Image.PreserveAspectFit }
                            HintText { anchors.horizontalCenter: parent.horizontalCenter; y: 3; visible: parent.recommended; text: "推荐"; font.pixelSize: 9; color: camp.ink }
                            HintText { anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 3; visible: parent.predicted; text: "推断"; font.pixelSize: 9; color: camp.secondary }
                            MouseArea { anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: page.openCell(index,parent) }
                        }
                    }
                }
                WarningNotice { objectName: "treasureFooter"; x: 5; y: 563; width: 438; height: 42
                    centeredText: true; textRightPadding: 32
                    emphasis: !!snapshot.boardWarning
                    text: snapshot.boardWarning || "优先探索未定位宝物；宝箱表示确认或推断占格。"
                    guidance: "点击地块手动标记未挖、空地或宝藏"
                }
            }
            Column { width: 280; spacing: 10
            Card {
                objectName: "configurationCard"; width: 280; height: 496; colorTheme: camp
                title: "棋盘设置"; icon: assetBase+"ui/treasure-grid.svg"; accent: camp.purple
                Column { x: 1; y: 9; width: 244; spacing: 8
                    Row { width: 244; height: 20; spacing: 18
                        LabelText { text: "本局宝物"; height: 20 }
                        WarningBadge { objectName: "configurationWarningBadge"; anchors.verticalCenter: parent.verticalCenter; detail: snapshot.configurationWarning }
                    }
                    ListView {
                        objectName: "treasureList"; width: 244; height: 282; clip: true; spacing: 8
                        model: Math.max(5,snapshot.shapes.length+1)
                        ScrollBar.vertical: ScrollBar { policy: snapshot.shapes.length>=5 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
                        delegate: Rectangle {
                            required property int index
                            property bool filled: index<snapshot.shapes.length
                            property var shape: filled ? snapshot.shapes[index] : [1,1,0]
                            objectName: "treasureRow"+index
                            width: 244; height: 50; radius: 10; color: filled ? camp.white : "transparent"
                            border.color: "#957455"; border.width: filled ? 1 : 0; opacity: filled ? 1 : rowAction.containsMouse ? .5 : .23
                            Canvas {
                                anchors.fill: parent; visible: !parent.filled
                                onPaint: { let ctx=getContext("2d");ctx.reset();ctx.strokeStyle="#957455";ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.beginPath();ctx.roundedRect(.5,.5,width-1,height-1,10,10);ctx.stroke() }
                            }
                            Rectangle { visible: parent.filled; x: 12; anchors.verticalCenter: parent.verticalCenter; width: Math.min(24,8*shape[0]); height: Math.min(28,8*shape[1]); radius: 2; color: camp.yellow; border.color: camp.border }
                            Column { x: 30; anchors.verticalCenter: parent.verticalCenter; visible: parent.filled
                                LabelText { text: shape[0]+" × "+shape[1]; height: 18 }
                                LabelText { text: "占 "+shape[0]*shape[1]+" 格"; height: 16; font.pixelSize: 10 }
                            }
                            MouseArea { id: rowAction; hoverEnabled: true; objectName: "treasureRowAction"+index; width: parent.filled ? 130 : parent.width; height: parent.height; cursorShape: Qt.PointingHandCursor; onClicked: page.openEditor(parent.filled ? index : -1) }
                            ActionButton { objectName: "quantityMinus"+index; visible: parent.filled; x: 132; y: 10; width: 30; height: 30; colorTheme: camp; iconPixels: 14; iconSource: assetBase+"ui/minus.svg"; onClicked: treasure.changeQuantity(index,-1) }
                            LabelText { visible: parent.filled; x: 165; y: 10; width: 16; height: 30; horizontalAlignment: Text.AlignHCenter; text: shape[2] }
                            ActionButton { objectName: "quantityPlus"+index; visible: parent.filled; x: 186; y: 10; width: 30; height: 30; colorTheme: camp; iconPixels: 14; iconSource: assetBase+"ui/plus.svg"; onClicked: treasure.changeQuantity(index,1) }
                        }
                    }
                    WarningNotice { objectName: "configurationWarning"; width: 244; height: 40
                        emphasis: !!snapshot.configurationWarning
                        text: snapshot.configurationWarning ? (page.calculationError ? "宝物或格子有误，请核对" : snapshot.configurationWarning.indexOf("估算")>=0 ? "宝物尺寸为估算，请核对" : "宝物识别有误，请修改") : snapshot.treasuresConfirmed ? "宝物已确认，点击宝物仍可修改" : "点击宝物修改尺寸与数量"
                        guidance: "点击空白处添加宝物，完成后确认"
                    }
                    ActionButton { objectName: "confirmTreasureButton"; width: 244; height: 30; colorTheme: camp; text: "确认宝物"; enabled: snapshot.shapes.length>0; onClicked: treasure.confirmTreasures() }
                    LabelText { text: "容量检查：已占 "+page.occupied+" / "+snapshot.size*snapshot.size+" 格"; height: 18; font.pixelSize: 10 }
                    Rectangle { width: 244; height: 6; radius: 3; color: camp.canvas
                        Rectangle { width: parent.width*Math.min(1,page.occupied/(snapshot.size*snapshot.size)); height: 6; radius: 3; color: camp.yellow }
                    }
                }
            }
                Card {
                    objectName: "estimateCard"; width: 280; height: 168; colorTheme: camp; panelRightInset: 1
                    title: "预计剩余消耗"; icon: assetBase+"ui/treasure-calculate.svg"; accent: camp.purple
                    Column {
                        id: estimateContent; x: 1; y: 65-height/2; width: 244; spacing: 4
                        Rectangle {
                            objectName: "estimateHighlight"; width: parent.width; height: 81; radius: 15
                            color: camp.estimateHighlight; visible: !page.calculationError
                            Column { x: 8; y: 8; width: parent.width-16; spacing: 0
                                Row { height: 44; spacing: 5; anchors.horizontalCenter: parent.horizontalCenter
                                    HintText { objectName: "estimateQualifier"; height: 44; text: page.consumptionMatch ? page.consumptionMatch[1] : ""; color: camp.ink; font.pixelSize: 14; font.weight: Font.Bold }
                                    LabelText { objectName: "estimatePrimary"; height: 44; text: page.consumptionMatch ? page.consumptionMatch[2] : page.consumptionPrimary; helpText: snapshot.status; font.pixelSize: page.consumptionMatch ? 32 : 16; font.weight: Font.Black }
                                    HintText { objectName: "estimateUnit"; height: 44; text: page.consumptionMatch ? "镐子" : ""; color: camp.ink; font.pixelSize: 14; font.weight: Font.Bold }
                                }
                                HintText { objectName: "estimateDetails"; width: parent.width; height: 21; horizontalAlignment: Text.AlignHCenter; text: page.consumptionGrid ? (page.consumptionMatch && page.consumptionMatch[1]==="还需" ? "剩余 " : "约 ")+page.consumptionGrid : ""; color: camp.ink; font.pixelSize: 12; font.weight: Font.Bold }
                            }
                        }
                        HintText { objectName: "estimateRandom"; horizontalAlignment: Text.AlignHCenter; visible: !page.calculationError; width: parent.width; height: Math.max(21,implicitHeight); text: (page.consumptionReference ? page.consumptionReference+"，" : "")+page.consumptionNote; helpText: text; wrapMode: Text.Wrap; lineHeightMode: Text.FixedHeight; lineHeight: 21; color: camp.secondary; font.pixelSize: 12; font.weight: Font.Bold }
                        WarningNotice { objectName: "estimateWarning"; width: parent.width; height: 110; visible: page.calculationError; emphasis: true; text: snapshot.status }
                    }
                }
            }
        }
    }
    NativePopup {
        id: cellPopup; objectName: "cellActionsPopup"; parent: page.Window.window.contentItem; property real uiScale: page.zoom; x: page.mapToItem(parent,page.popupLeft,page.popupTop).x; y: page.mapToItem(parent,page.popupLeft,page.popupTop).y
        implicitWidth: 294*uiScale; implicitHeight: 46*uiScale; width: implicitWidth; height: implicitHeight; padding: 8*uiScale; closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: PopupSurface {}
        contentItem: Item { Row { spacing: 6; scale: cellPopup.uiScale; transformOrigin: Item.TopLeft
            Repeater { model: ["标为空地","标为宝藏","恢复未挖"]
                delegate: ActionButton { required property int index; required property string modelData; objectName: "cellAction"+index; width: 88; height: 29; colorTheme: camp; text: modelData; onClicked: { treasure.mark(page.selectedCell,[1,2,0][index]);cellPopup.close() } }
            }
        } }
    }
    DialogTheme { id: dialogTheme }
    AppDialog {
        id: treasureDialog; objectName: "treasureDialog"; parent: page.Window.window.contentItem; uiScale: page.zoom; preferredWidth: 320; colorTheme: camp
        contentPadding: 20; dialogVerticalInset: 20; sectionSpacing: 18; headingSize: 16; headingHeight: 24; buttonHeight: 34
        title: page.editingIndex<0 ? "添加宝物" : "修改宝物"
        acceptText: page.editingIndex<0 ? "添加" : "保存"
        acceptObjectName: "saveTreasureButton"; showCancel: true; closeOnAccept: false
        acceptTone: camp.yellow; errorText: page.editError
        onAccepted: {
            if(widthInput.acceptableInput && heightInput.acceptableInput && quantityInput.acceptableInput && treasure.editTreasure(page.editingIndex,Number(widthInput.text),Number(heightInput.text),Number(quantityInput.text)))close()
            else page.editError="尺寸、数量或总占格无效"
        }
        Row { width: parent.width; spacing: 14
            Column { width: (parent.width-28)/3; spacing: 6
                LabelText { width: parent.width; height: 18; horizontalAlignment: Text.AlignHCenter; text: "宽" }
                Field { id: widthInput; objectName: "treasureWidthInput"; colorTheme: camp; width: parent.width; height: 34; validator: IntValidator { bottom: 1; top: snapshot.size } }
            }
            Column { width: (parent.width-28)/3; spacing: 6
                LabelText { width: parent.width; height: 18; horizontalAlignment: Text.AlignHCenter; text: "高" }
                Field { id: heightInput; objectName: "treasureHeightInput"; colorTheme: camp; width: parent.width; height: 34; validator: IntValidator { bottom: 1; top: snapshot.size } }
            }
            Column { width: (parent.width-28)/3; spacing: 6
                LabelText { width: parent.width; height: 18; horizontalAlignment: Text.AlignHCenter; text: "数量" }
                Field { id: quantityInput; objectName: "treasureQuantityInput"; colorTheme: camp; width: parent.width; height: 34; validator: IntValidator { bottom: page.editingIndex<0 ? 1 : 0; top: 20 } helpText: "设为0可删除宝物" }
            }
        }
    }
    AppDialog { id: clearDialog; objectName: "clearMarksDialog"; parent: page.Window.window.contentItem; uiScale: page.zoom; colorTheme: camp; title: "清空标记"; message: "清空所有格子标记？可撤销。"; acceptText: "清空"; showCancel: true; onAccepted: treasure.clear() }
    AppDialog { id: sizeDialog; objectName: "boardSizeDialog"; parent: page.Window.window.contentItem; uiScale: page.zoom; colorTheme: camp; title: "修改棋盘"; message: "修改尺寸会清空格子标记。"; acceptText: "修改"; showCancel: true; onAccepted: treasure.editBoard(Number(sizeInput.text),snapshot.cost); onClosed: sizeInput.text=snapshot.size }
}
