/*
 * 统御至诚 - SDDM 登录主题
 * Logo + 统御至诚 + 系统名称 + 登录表单
 * 使用 config 避免空内容报错
 */
import QtQuick 2.15
import SddmComponents 2.0

Rectangle {
    id: root
    width: 640
    height: 480

    LayoutMirroring.enabled: Qt.locale().textDirection == Qt.RightToLeft
    LayoutMirroring.childrenInherit: true

    // 可配置文本（避免空值）
    property string systemName: config.stringValue("SystemName") || "统御至诚云桌面"
    property string slogan: config.stringValue("Slogan") || "统御至诚"
    property string logoPath: config.stringValue("LogoPath") || "images/logo.png"
    property string logoPathSvg: "images/logo.svg"

    TextConstants { id: textConstants }

    Connections {
        target: sddm
        onLoginSucceeded: {}
        onLoginFailed: {
            pw_entry.text = ""
            pw_entry.focus = true
        }
    }

    // 背景渐变（蓝色系）
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#0d47a1" }
            GradientStop { position: 0.5; color: "#1565c0" }
            GradientStop { position: 1.0; color: "#0d47a1" }
        }
    }

    // 顶部品牌区：Logo + 统御至诚 + 系统名称
    Column {
        id: brandArea
        anchors {
            top: parent.top
            horizontalCenter: parent.horizontalCenter
            topMargin: 40
        }
        spacing: 12

        Image {
            id: logo
            anchors.horizontalCenter: parent.horizontalCenter
            width: 80
            height: 60
            fillMode: Image.PreserveAspectFit
            source: Qt.resolvedUrl(logoPath)
            visible: status === Image.Ready
        }
        Image {
            id: logoSvg
            anchors.horizontalCenter: parent.horizontalCenter
            width: 80
            height: 60
            fillMode: Image.PreserveAspectFit
            source: Qt.resolvedUrl(logoPathSvg)
            visible: logo.status !== Image.Ready && status === Image.Ready
        }

        Text {
            text: slogan
            color: "#ffffff"
            font.pixelSize: 28
            font.bold: true
            anchors.horizontalCenter: parent.horizontalCenter
        }

        Text {
            text: systemName
            color: "rgba(255,255,255,0.9)"
            font.pixelSize: 14
            anchors.horizontalCenter: parent.horizontalCenter
        }
    }

    // 登录表单
    Rectangle {
        id: loginBox
        width: 360
        height: 200
        color: "rgba(255,255,255,0.1)"
        radius: 8
        anchors.centerIn: parent
        anchors.verticalCenterOffset: 30

        Column {
            anchors.centerIn: parent
            spacing: 16

            Row {
                TextBox {
                    id: user_entry
                    radius: 4
                    width: 280
                    text: userModel.lastUser || ""
                    font.pixelSize: 14
                    color: "rgba(255,255,255,0.15)"
                    borderColor: "transparent"
                    focusColor: "rgba(255,255,255,0.3)"
                    hoverColor: "rgba(255,255,255,0.2)"
                    textColor: "white"
                    KeyNavigation.tab: pw_entry
                }
            }

            Row {
                PasswordBox {
                    id: pw_entry
                    radius: 4
                    width: 280
                    font.pixelSize: 14
                    color: "rgba(255,255,255,0.15)"
                    borderColor: "transparent"
                    focusColor: "rgba(255,255,255,0.3)"
                    hoverColor: "rgba(255,255,255,0.2)"
                    textColor: "white"
                    focus: true
                    KeyNavigation.backtab: user_entry
                    KeyNavigation.tab: loginButton
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                            sddm.login(user_entry.text, pw_entry.text, session.index)
                            event.accepted = true
                        }
                    }
                }
            }

            Button {
                id: loginButton
                radius: 4
                text: textConstants.login
                width: 280
                color: "rgba(255,255,255,0.2)"
                activeColor: "rgba(255,255,255,0.25)"
                pressedColor: "rgba(255,255,255,0.3)"
                font.pixelSize: 14
                onClicked: sddm.login(user_entry.text, pw_entry.text, session.index)
                KeyNavigation.backtab: pw_entry
                KeyNavigation.tab: session
            }
        }
    }

    // 底部：会话选择 + 电源
    Row {
        anchors {
            bottom: parent.bottom
            horizontalCenter: parent.horizontalCenter
            bottomMargin: 20
        }
        spacing: 12

        ComboBox {
            id: session
            width: 180
            arrowIcon: Qt.resolvedUrl("images/angle-down.svg")
            model: sessionModel
            index: sessionModel.lastIndex
            font.pixelSize: 12
            color: "rgba(255,255,255,0.15)"
            borderColor: "transparent"
            KeyNavigation.backtab: loginButton
            KeyNavigation.tab: btnReboot
        }

        Button {
            id: btnReboot
            text: textConstants.reboot
            visible: sddm.canReboot
            font.pixelSize: 12
            color: "rgba(255,255,255,0.15)"
            onClicked: sddm.reboot()
            KeyNavigation.backtab: session
            KeyNavigation.tab: btnShutdown
        }

        Button {
            id: btnShutdown
            text: textConstants.shutdown
            visible: sddm.canPowerOff
            font.pixelSize: 12
            color: "rgba(255,255,255,0.15)"
            onClicked: sddm.powerOff()
            KeyNavigation.backtab: btnReboot
            KeyNavigation.tab: user_entry
        }
    }

    Component.onCompleted: {
        if (!user_entry.text || user_entry.text === "")
            user_entry.focus = true
        else
            pw_entry.focus = true
    }
}
