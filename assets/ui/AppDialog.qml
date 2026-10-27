import QtQuick
import QtQuick.Controls.Basic
NativePopup {
    id: dialog
    centerInOwner: true
    property string title: "提示"
    property string message: ""
    property string errorText: ""
    property string acceptText: "知道了"
    property string cancelText: "取消"
    property string acceptObjectName: "dialogAcceptButton"
    property bool showCancel: false
    property bool closeOnAccept: true
    property real preferredWidth: 0
    property real uiScale: 1
    property var colorTheme: null
    readonly property var activeTheme: colorTheme || theme
    property real contentPadding: 24
    property real dialogVerticalInset: 22
    property real sectionSpacing: 20
    property real headingSize: 15
    property real headingHeight: 22
    property real buttonHeight: 38
    property color acceptTone: activeTheme.refresh
    default property alias bodyData: body.data
    signal accepted()
    signal rejected()
    function accept() { accepted(); if(closeOnAccept)close() }
    function reject() { rejected(); close() }
    x: (parent.width-width)/2
    y: (parent.height-height)/2
    implicitWidth: Math.min(parent.width-24*uiScale, (preferredWidth>0 ? preferredWidth : Math.max(showCancel ? 264 : 172, Math.min(420, Math.max(heading.implicitWidth, copy.implicitWidth)+52)))*uiScale)
    implicitHeight: (contentColumn.implicitHeight+2*dialogVerticalInset)*uiScale
    width: implicitWidth; height: implicitHeight
    padding: contentPadding*uiScale
    topPadding: dialogVerticalInset*uiScale; bottomPadding: dialogVerticalInset*uiScale
    modal: true; focus: true
    background: PopupSurface { color: dialog.activeTheme.surface; radius: dialog.colorTheme ? 18 : 15; shadowTone: dialog.colorTheme ? dialog.colorTheme.shadow : "transparent" }
    DialogTheme { id: theme }
    onOpened: contentColumn.forceActiveFocus()
    contentItem: Item {
      Column {
        id: contentColumn; spacing: dialog.sectionSpacing; width: parent.width/dialog.uiScale
        scale: dialog.uiScale; transformOrigin: Item.TopLeft
        focus: true
        Keys.onEscapePressed: dialog.reject()
        LabelText { id: heading; width: parent.width; height: dialog.headingHeight; text: dialog.title; font.pixelSize: dialog.headingSize; horizontalAlignment: Text.AlignHCenter }
        Flickable {
            visible: dialog.message!==""; width: parent.width
            height: Math.min(copy.implicitHeight, Math.max(60,(dialog.parent ? dialog.parent.height : 800)/dialog.uiScale-220))
            contentHeight: copy.implicitHeight; clip: true
            boundsBehavior: Flickable.StopAtBounds
            LabelText { id: copy; width: parent.width; text: dialog.message; font.pixelSize: 15; lineHeightMode: Text.FixedHeight; lineHeight: 22; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter }
            ScrollBar.vertical: ScrollBar {}
        }
        Column { id: body; width: parent.width; spacing: 12; visible: children.length>0 }
        WarningNotice { objectName: "dialogErrorNotice"; visible: dialog.errorText!==""; width: parent.width; text: dialog.errorText }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter; spacing: 12; height: dialog.buttonHeight
            ActionButton { objectName: dialog.acceptObjectName; width: dialog.showCancel ? (contentColumn.width-12)/2 : 96; height: dialog.buttonHeight; colorTheme: dialog.activeTheme; tone: dialog.acceptTone; text: dialog.acceptText; onClicked: dialog.accept() }
            ActionButton { objectName: "dialogCancelButton"; visible: dialog.showCancel; width: (contentColumn.width-12)/2; height: dialog.buttonHeight; colorTheme: dialog.activeTheme; text: dialog.cancelText; onClicked: dialog.reject() }
        }
      }
    }
}
