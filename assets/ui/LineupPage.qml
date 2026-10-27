import QtQuick
import QtQuick.Controls.Basic
Column {
    id: page
    property var s: lineup.state
    property int selectedCell: -1
    property bool cropping: false
    property var results: []
    readonly property real naturalHeight: implicitHeight
    LineupTheme { id: theme }
    spacing: 14
    Shortcut { sequence: "Ctrl+V"; enabled: visible && !editor.visible; onActivated: lineup.pasteImage() }
    Rectangle {
        width: parent.width; height: connection.implicitHeight+32; radius: 16; color: theme.surface; border.color: theme.ink; border.width: 2
        Column {
            id: connection; x: 16; y: 16; width: parent.width-32; spacing: 10
            Row {
                width: parent.width; spacing: 10
                LabelText { color: theme.ink; width: 84; text: "操作模式"; anchors.verticalCenter: parent.verticalCenter }
                Picker { objectName: "lineupModePicker"; colorTheme: theme; width: connection.width-94; model: ["后台 MuMuSDK", "前台 Maa", "通用后台 ADB + MaaTouch"]; currentIndex: page.s.modeIndex; enabled: !page.s.running; onActivated: lineup.setMode(currentIndex) }
            }
            Row {
                width: parent.width; spacing: 10
                LabelText { color: theme.ink; width: 84; text: "游戏设备"; anchors.verticalCenter: parent.verticalCenter }
                Picker { objectName: "lineupDevicePicker"; colorTheme: theme; width: connection.width-164; model: page.s.devices; currentIndex: page.s.deviceIndex; displayText: currentIndex>=0 ? currentText : "请选择设备"; enabled: !page.s.running; onActivated: lineup.selectDevice(currentIndex) }
                ActionButton { colorTheme: theme; width: 60; text: page.s.refreshing ? "查找中" : "刷新"; enabled: !page.s.running && !page.s.refreshing; tone: theme.refresh; onClicked: lineup.refresh() }
            }
            Field { colorTheme: theme; visible: page.s.modeIndex===2; width: parent.width; placeholderText: "ADB 地址，例如 127.0.0.1:16384"; enabled: !page.s.running; onEditingFinished: lineup.setAddress(text) }
            Row {
                spacing: 10
                HintText { color: theme.secondary; width: 84; text: "画面边距"; anchors.verticalCenter: parent.verticalCenter }
                HintText { color: theme.secondary; text: "顶部"; anchors.verticalCenter: parent.verticalCenter }
                Field { colorTheme: theme; width: 66; text: String(page.s.crop_top); enabled: !page.s.running; onEditingFinished: lineup.setValue("crop_top",text) }
                HintText { color: theme.secondary; text: "底部"; anchors.verticalCenter: parent.verticalCenter }
                Field { colorTheme: theme; width: 66; text: String(page.s.crop_bottom); enabled: !page.s.running; onEditingFinished: lineup.setValue("crop_bottom",text) }
                HintText { color: theme.secondary; text: "0 = 自动识别"; anchors.verticalCenter: parent.verticalCenter }
            }
        }
    }
    Rectangle {
        width: parent.width; height: importer.implicitHeight+32; radius: 16; color: theme.surface; border.color: theme.ink; border.width: 2
        Column {
            id: importer; x: 16; y: 16; width: parent.width-32; spacing: 12
            Row {
                width: parent.width
                LabelText { color: theme.ink; width: parent.width-80; text: "阵容图片"; font.pixelSize: 15; anchors.verticalCenter: parent.verticalCenter }
                ActionButton { colorTheme: theme; objectName: "lineupScreenshot"; width: 80; text: "截图"; tone: theme.refresh; enabled: !page.s.running && !page.s.importing; onClicked: lineup.screenshot() }
            }
            Rectangle {
                id: drop; objectName: "lineupDrop"; width: parent.width; height: 156; radius: 12; color: "#f4f9ee"; border.color: theme.border; border.width: 1
                Image { id: sourceImage; objectName: "lineupSource"; anchors.fill: parent; anchors.margins: 5; source: page.s.source; fillMode: Image.PreserveAspectFit; cache: false; smooth: true }
                Rectangle {
                    anchors.fill: parent; radius: 12; color: "#ccedf4e6"; visible: page.s.importing; z: 2
                    Column { anchors.centerIn: parent; spacing: 8
                        LabelText { color: theme.ink; objectName: "lineupRecognizing"; anchors.horizontalCenter: parent.horizontalCenter; text: "识别中"; font.pixelSize: 18 }
                        HintText { color: theme.secondary; anchors.horizontalCenter: parent.horizontalCenter; text: page.s.importStatus; font.pixelSize: 11 }
                    }
                }
                Column { anchors.centerIn: parent; visible: !page.s.source; spacing: 10
                    LabelText { color: theme.ink; anchors.horizontalCenter: parent.horizontalCenter; text: "拖入或点击选择图片"; font.pixelSize: 16 }
                    HintText { color: theme.secondary; anchors.horizontalCenter: parent.horizontalCenter; text: "支持截图后直接粘贴，导入即开始上阵" }
                }
                Rectangle {
                    id: cropBox; visible: cropMouse.pressed && page.cropping; color: "#33ffd65a"; border.color: "#f2b500"; border.width: 2
                    x: Math.min(cropMouse.start.x,cropMouse.end.x); y: Math.min(cropMouse.start.y,cropMouse.end.y)
                    width: Math.abs(cropMouse.end.x-cropMouse.start.x); height: Math.abs(cropMouse.end.y-cropMouse.start.y)
                }
                MouseArea {
                    id: cropMouse; anchors.fill: parent; enabled: !page.s.running && !page.s.importing
                    cursorShape: page.cropping ? Qt.CrossCursor : Qt.PointingHandCursor
                    property point start; property point end
                    onPressed: function(mouse) { start=Qt.point(mouse.x,mouse.y);end=start }
                    onPositionChanged: function(mouse) { if(pressed)end=Qt.point(mouse.x,mouse.y) }
                    onReleased: function(mouse) {
                        end=Qt.point(mouse.x,mouse.y)
                        if(!page.cropping) { lineup.chooseImage(); return }
                        let scale=Math.min(sourceImage.width/page.s.sourceWidth,sourceImage.height/page.s.sourceHeight)
                        let ox=sourceImage.x+(sourceImage.width-page.s.sourceWidth*scale)/2
                        let oy=sourceImage.y+(sourceImage.height-page.s.sourceHeight*scale)/2
                        let left=Math.max(0,(cropBox.x-ox)/scale),top=Math.max(0,(cropBox.y-oy)/scale)
                        let right=Math.min(page.s.sourceWidth,(cropBox.x+cropBox.width-ox)/scale),bottom=Math.min(page.s.sourceHeight,(cropBox.y+cropBox.height-oy)/scale)
                        lineup.recognize([left,top,right-left,bottom-top]);page.cropping=false
                    }
                }
                DropArea { anchors.fill: parent; enabled: !page.s.running && !page.s.importing
                    onDropped: function(drop) { if(drop.hasUrls && drop.urls.length) { lineup.loadImage(drop.urls[0]);drop.acceptProposedAction() } }
                }
            }
            Row {
                spacing: 10; width: parent.width
                HintText { color: theme.secondary; text: "阵型"; anchors.verticalCenter: parent.verticalCenter }
                Picker { objectName: "lineupGridPicker"; colorTheme: theme; width: 86; model: ["5 × 5", "3 × 4"]; currentIndex: page.s.columns===5 ? 0 : 1; enabled: !page.s.running && !page.s.importing; onActivated: lineup.setColumns(currentIndex===0 ? 5 : 3) }
                ActionButton { colorTheme: theme; width: 106; text: page.cropping ? "拖拽框选中" : "框选阵型"; tone: page.cropping ? "#ffd65a" : theme.refresh; enabled: !!page.s.source && !page.s.running && !page.s.importing; onClicked: page.cropping=!page.cropping }
                ActionButton { colorTheme: theme; width: 96; text: "自动识别"; tone: theme.refresh; enabled: !!page.s.source && !page.s.running && !page.s.importing; onClicked: lineup.recognize([]) }
                HintText { color: theme.secondary; text: "敌人在上方"; anchors.verticalCenter: parent.verticalCenter }
            }
        }
    }
    Rectangle {
        width: parent.width; height: preview.implicitHeight+32; radius: 16; color: theme.surface; border.color: theme.ink; border.width: 2
        Column {
            id: preview; x: 16; y: 16; width: parent.width-32; spacing: 12
            Row {
                width: parent.width
                LabelText { color: theme.ink; width: parent.width-160; text: "上阵预览"; font.pixelSize: 15 }
                HintText { color: theme.secondary; text: "资料库 "+page.s.catalogCount+" 只"; font.pixelSize: 11 }
            }
            Grid {
                anchors.horizontalCenter: parent.horizontalCenter; columns: page.s.columns; spacing: 6
                Repeater {
                    model: page.s.cells
                    Rectangle {
                        required property var modelData; required property int index
                        objectName: "lineupTile"+index
                        width: 48; height: 48; radius: 8; color: modelData.id==="?" || modelData.reason ? "#ffddd5" : "#f4f9ee"; border.color: modelData.id==="?" || modelData.reason ? "#e66c57" : theme.border
                        Image { anchors.fill: parent; anchors.margins: 3; source: modelData.image; fillMode: Image.PreserveAspectFit; smooth: true; mipmap: true }
                        LabelText { color: theme.ink; anchors.centerIn: parent; text: modelData.id==="?" ? "?" : ""; font.pixelSize: 24 }
                        HintText { color: theme.secondary; anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 3; text: modelData.stage ? "T"+modelData.stage : ""; font.pixelSize: 9 }
                        MouseArea { id: tileMouse; anchors.fill: parent; enabled: !page.s.running && !page.s.importing; hoverEnabled: true
                            onClicked: editor.openCell(index)
                        }
                        HelpTip { text: (modelData.name || "空位 · 点击添加")+(modelData.reason ? " · "+modelData.reason : ""); visible: tileMouse.containsMouse }
                    }
                }
            }
            HintText { color: theme.secondary; width: parent.width; text: "点击格子可更正、添加或清空；不确定的塔塔会标为问号。"; wrapMode: Text.WordWrap; font.pixelSize: 11 }
            HintText { color: theme.secondary; width: parent.width; text: "缺少指定阶段时使用同一进化链的库存阶段；先完成已确认部分。"; wrapMode: Text.WordWrap; font.pixelSize: 11 }
            CheckBox { text: "在模拟器上标注未完成位置"; checked: page.s.overlayEnabled; font.family: "Chiron GoRound TC"; font.pixelSize: 12; onToggled: lineup.setValue("overlayEnabled",checked) }
        }
    }
    HintText { color: theme.secondary; width: parent.width; text: page.s.columns===3 ? "导入图片即开始识别并上阵。3 × 4 最多 5 只同属性塔塔，请停留在上阵界面。" : "导入图片即开始识别并上阵，已确认的塔塔先行部署。请停留在游戏上阵界面。"; wrapMode: Text.WordWrap; font.pixelSize: 11 }
    Row {
        width: parent.width; spacing: 16
        ActionButton { colorTheme: theme; objectName: "lineupStart"; width: (page.width-16)/2; large: true; centeredLabel: true; text: "一键上阵"; shortcut: "Home"; tone: "#daf6b7"; enabled: !page.s.running && !page.s.importing && !page.s.autoPending && !page.s.refreshing && !page.s.exporting; onClicked: lineup.start() }
        ActionButton { colorTheme: theme; objectName: "lineupStop"; width: (page.width-16)/2; large: true; centeredLabel: true; text: "停止"; shortcut: "PgDown"; tone: "#ffaaa0"; enabled: page.s.running || page.s.importing || page.s.autoPending; onClicked: lineup.stop() }
    }
    Rectangle {
        width: parent.width; height: statusColumn.implicitHeight+24; radius: 12; color: theme.refresh
        Column {
            id: statusColumn; x: 12; y: 12; width: parent.width-24; spacing: 6
            LabelText { color: theme.ink; width: parent.width; text: page.s.status; wrapMode: Text.WordWrap; font.pixelSize: 12 }
            HintText { color: theme.secondary; width: parent.width; text: "已完成 "+page.s.completed+" 只 · 库存已确认 "+page.s.inventoryFound+" 只 · 当前上阵 "+(page.s.count===null || page.s.count===undefined ? "—" : page.s.count)+" / "+(page.s.limit===null || page.s.limit===undefined ? "—" : page.s.limit); wrapMode: Text.WordWrap; font.pixelSize: 11 }
            Row { width: parent.width; spacing: 10
                HintText { color: theme.secondary; width: parent.width-216; text: page.s.diagnosticHint; wrapMode: Text.WordWrap; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter }
                ActionButton { objectName: "lineupOpenDiagnostics"; colorTheme: theme; width: 84; text: "打开记录"; tone: theme.surface; enabled: !page.s.running && !page.s.importing && !page.s.autoPending && !page.s.exporting; onClicked: lineup.openDiagnostics() }
                ActionButton { objectName: "lineupExportDiagnostics"; colorTheme: theme; width: 112; text: page.s.exporting ? "正在导出" : "导出诊断包"; tone: theme.surface; enabled: !page.s.running && !page.s.importing && !page.s.autoPending && !page.s.exporting; onClicked: lineup.exportDiagnostics() }
            }
            Repeater { model: page.s.outside
                HintText { color: theme.secondary; required property var modelData; text: "第 "+(modelData.sourceIndex+1)+" 格："+modelData.reason; font.pixelSize: 11 }
            }
        }
    }
    NativePopup {
        id: editor; objectName: "lineupEditor"; implicitWidth: (page.width-24)*uiScale; implicitHeight: 450*uiScale; width: implicitWidth; height: implicitHeight; padding: 16*uiScale
        property real uiScale: page.Window.window ? page.Window.window.visualZoom : 1
        parent: page.Window.window.contentItem
        x: (parent.width-width)/2; y: (parent.height-height)/2
        modal: true; focus: true
        centerInOwner: true
        background: PopupSurface { color: theme.surface; border.color: theme.ink }
        function openCell(index) {
            page.selectedCell=index;searchField.text="";page.results=lineup.search("")
            open();searchField.forceActiveFocus()
        }
        Connections { target: page; function onVisibleChanged() { if(!page.visible)editor.close() } }
        contentItem: Item { Column {
            width: parent.width/editor.uiScale; height: parent.height/editor.uiScale; spacing: 12
            scale: editor.uiScale; transformOrigin: Item.TopLeft
            Row { width: parent.width
                LabelText { color: theme.ink; text: "修正第 "+(page.selectedCell+1)+" 格"; width: parent.width-88; font.pixelSize: 16 }
                ActionButton { colorTheme: theme; width: 88; text: "设为空位"; onClicked: { lineup.setCell(page.selectedCell,"");editor.close() } }
            }
            Field { colorTheme: theme; id: searchField; width: parent.width; placeholderText: "搜索塔塔名称"; onTextChanged: page.results=lineup.search(text) }
            ListView {
                width: parent.width; height: 324; model: page.results; clip: true; spacing: 4
                ScrollBar.vertical: ScrollBar {}
                delegate: Rectangle {
                    required property var modelData
                    width: ListView.view.width; height: 48; color: candidateMouse.containsMouse ? theme.refresh : theme.surface; radius: 8
                    Image { x: 6; y: 4; width: 40; height: 40; source: modelData.image; fillMode: Image.PreserveAspectFit; smooth: true }
                    LabelText { color: theme.ink; x: 54; y: 16; width: parent.width-62; text: modelData.name; font.pixelSize: 12; elide: Text.ElideRight }
                    MouseArea { id: candidateMouse; anchors.fill: parent; hoverEnabled: true; onClicked: { lineup.setCell(page.selectedCell,modelData.id);editor.close() } }
                }
            }
        } }
    }
}
