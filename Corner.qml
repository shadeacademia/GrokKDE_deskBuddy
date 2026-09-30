import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import org.kde.layershell as LayerShell

Window {
    id: win
    title: "Grok Corner"
    color: "transparent"
    flags: Qt.FramelessWindowHint
    visible: true

    readonly property int pad: 18
    // 15 mm. Screen.pixelDensity is logical pixels per mm on this desktop.
    readonly property int shiftLeft: Math.round(15 * (Screen.pixelDensity > 0 ? Screen.pixelDensity : 1.2))
    readonly property int padX: pad + shiftLeft
    readonly property int markSize: 56
    readonly property int logoInset: 8
    readonly property int hit: markSize - logoInset * 2
    readonly property int panelW: 400
    readonly property int panelH: 540
    readonly property int gap: 12
    property bool expanded: startExpanded
    property bool armOutside: false
    property bool menuOpen: false
    readonly property int menuW: 220

    width: expanded ? panelW : (menuOpen ? menuW : hit)
    height: expanded ? panelH + gap + hit : (menuOpen ? contextMenu.height + gap + hit : hit)

    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorRight | LayerShell.Window.AnchorBottom
    LayerShell.Window.margins.right: padX + logoInset
    LayerShell.Window.margins.bottom: pad + logoInset
    LayerShell.Window.margins.left: 0
    LayerShell.Window.margins.top: 0
    LayerShell.Window.exclusionZone: 0
    LayerShell.Window.keyboardInteractivity: expanded
        ? LayerShell.Window.KeyboardInteractivityOnDemand
        : LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.activateOnShow: false

    onActiveChanged: {
        if (!active && expanded && armOutside)
            closePanel()
        if (!active && menuOpen && menuArmed)
            menuOpen = false
    }

    function openMenu() {
        menuArmed = false
        corner.refresh()
        menuOpen = true
        menuArm.restart()
    }

    property bool menuArmed: false

    Timer {
        id: menuArm
        interval: 200
        repeat: false
        onTriggered: win.menuArmed = true
    }

    function openPanel() {
        armOutside = false
        expanded = true
        focusTimer.restart()
    }

    function closePanel() {
        armOutside = false
        expanded = false
        input.focus = false
    }

    function toggle() {
        if (expanded)
            closePanel()
        else
            openPanel()
    }

    Timer {
        id: focusTimer
        interval: 80
        repeat: false
        onTriggered: {
            input.forceActiveFocus()
            armOutside = true
        }
    }

    Component.onCompleted: {
        console.log("corner screen", Screen.width, Screen.height, "window", width, height, "hit", hit)
        if (startExpanded)
            openPanel()
    }

    Item {
        anchors.fill: parent

        Rectangle {
            id: panel
            visible: win.expanded
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: mark.top
            anchors.bottomMargin: win.gap
            radius: 18
            color: "#17181c"
            border.color: "#3a3b44"
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 10

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text {
                        text: "GROK"
                        color: "#d8d8de"
                        font.pixelSize: 12
                        font.letterSpacing: 2.4
                        font.weight: Font.Medium
                    }

                }

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                ListView {
                    id: list
                    anchors.fill: parent
                    clip: true
                    spacing: 12
                    boundsBehavior: Flickable.StopAtBounds
                    model: corner.messages
                    visible: count > 0

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }

                    delegate: Item {
                        required property string who
                        required property string body
                        required property int index
                        width: list.width
                        height: line.implicitHeight

                        Rectangle {
                            visible: who === "user"
                            anchors.fill: line
                            radius: 12
                            color: "#26272e"
                        }

                        Text {
                            id: line
                            width: who === "user" ? Math.min(implicitWidth + 20, list.width * 0.86) : list.width
                            anchors.right: who === "user" ? parent.right : undefined
                            text: body === "" ? "…" : body
                            color: body === "" ? "#8e8f99" : "#f3f3f5"
                            wrapMode: Text.Wrap
                            font.pixelSize: 15
                            lineHeight: 1.25
                            lineHeightMode: Text.ProportionalHeight
                            leftPadding: who === "user" ? 10 : 0
                            rightPadding: who === "user" ? 10 : 0
                            topPadding: who === "user" ? 8 : 0
                            bottomPadding: who === "user" ? 8 : 0
                        }
                    }

                    onCountChanged: Qt.callLater(positionViewAtEnd)
                }

                Text {
                    visible: list.count === 0
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    text: "This chat lasts until you log out."
                    color: "#8e8f99"
                    font.pixelSize: 14
                    wrapMode: Text.Wrap
                }
                }

                RowLayout {
                    visible: corner.activity !== ""
                    Layout.fillWidth: true
                    spacing: 8

                    Rectangle {
                        id: statusDot
                        Layout.alignment: Qt.AlignVCenter
                        width: 8
                        height: 8
                        radius: 4
                        color: corner.activity === "Stopped" ? "#e0a050" : "#f4f4f5"

                        SequentialAnimation on opacity {
                            running: corner.busy
                            loops: Animation.Infinite
                            NumberAnimation { to: 0.25; duration: 700 }
                            NumberAnimation { to: 1; duration: 700 }
                            onRunningChanged: {
                                if (!running)
                                    statusDot.opacity = 1
                            }
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        text: corner.activity
                        color: corner.activity === "Stopped" ? "#e0a050" : "#d8d8de"
                        font.pixelSize: 14
                        elide: Text.ElideMiddle
                    }
                }

                TextArea {
                    id: input
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(Math.max(implicitHeight, 44), 120)
                    placeholderText: "Ask Grok"
                    placeholderTextColor: "#7d7e88"
                    color: "#f4f4f5"
                    wrapMode: TextEdit.Wrap
                    selectByMouse: true
                    padding: 10
                    font.pixelSize: 15
                    background: Rectangle {
                        radius: 12
                        color: "#0d0e11"
                        border.color: input.activeFocus ? "#3c3d46" : "#2a2b31"
                    }

                    Keys.onPressed: (event) => {
                        if (event.key === Qt.Key_Escape) {
                            win.closePanel()
                            event.accepted = true
                        } else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                                   && !(event.modifiers & Qt.ShiftModifier)) {
                            corner.send(input.text)
                            input.text = ""
                            event.accepted = true
                        }
                    }
                }
            }
        }

        Rectangle {
            id: contextMenu
            visible: win.menuOpen
            z: 2
            width: win.menuW
            height: menuCol.implicitHeight + 12
            anchors.right: parent.right
            anchors.bottom: mark.top
            anchors.bottomMargin: win.gap
            radius: 14
            color: "#17181c"
            border.width: 1
            border.color: "#3a3b44"

            component MenuRow: Rectangle {
                id: row
                required property string label
                property string stateText: ""
                property bool dimmed: false
                signal triggered()
                width: menuCol.width
                height: 36
                radius: 8
                color: area.containsMouse && !row.dimmed ? "#26272e" : "transparent"
                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: row.label
                    color: row.dimmed ? "#8e8f99" : "#f4f4f5"
                    font.pixelSize: 14
                }
                Text {
                    visible: row.stateText !== ""
                    anchors.right: parent.right
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: row.stateText
                    color: "#8e8f99"
                    font.pixelSize: 13
                }
                MouseArea {
                    id: area
                    anchors.fill: parent
                    hoverEnabled: true
                    enabled: !row.dimmed
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: row.triggered()
                }
            }

            Column {
                id: menuCol
                x: 6
                y: 6
                width: parent.width - 12
                spacing: 2

                MenuRow {
                    label: corner.signingIn ? "Signing in…" : (corner.signedIn ? "Log out" : "Log in")
                    dimmed: corner.signingIn
                    onTriggered: {
                        if (corner.signedIn)
                            corner.logout()
                        else
                            corner.login()
                    }
                }
                MenuRow {
                    label: "Autostart"
                    stateText: corner.autostart ? "On" : "Off"
                    onTriggered: corner.setAutostart(!corner.autostart)
                }
                Rectangle {
                    width: menuCol.width
                    height: 9
                    color: "transparent"
                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        height: 1
                        color: "#2e2f36"
                    }
                }
                MenuRow {
                    label: "Exit"
                    onTriggered: corner.quit()
                }
            }
        }

        Item {
            id: mark
            z: 3
            width: win.hit
            height: win.hit
            anchors.right: parent.right
            anchors.bottom: parent.bottom

            Image {
                id: logo
                anchors.fill: parent
                source: Qt.resolvedUrl("grok-mark.png")
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true

                SequentialAnimation on opacity {
                    id: pulse
                    running: corner.busy
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.25; duration: 700 }
                    NumberAnimation { to: 1; duration: 700 }
                    onRunningChanged: {
                        if (!running)
                            logo.opacity = 1
                    }
                }
            }

            MouseArea {
                id: markArea
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                cursorShape: Qt.PointingHandCursor
                onClicked: (mouse) => {
                    if (mouse.button === Qt.RightButton) {
                        if (win.menuOpen)
                            win.menuOpen = false
                        else
                            win.openMenu()
                        return
                    }
                    win.menuOpen = false
                    win.toggle()
                }
            }
        }
    }

    Connections {
        target: corner
        function onBumped() {
            Qt.callLater(list.positionViewAtEnd)
        }
    }
}
