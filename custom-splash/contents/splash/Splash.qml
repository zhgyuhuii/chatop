/*
 * 统御至诚 - 自定义开机动画
 * 渐变背景、Logo 缩放、旋转加载、文字淡入
 * 使用 QtQuick 2.5，避免 ksplashqml 崩溃
 */

import QtQuick 2.5
import QtQuick.Window 2.2

Rectangle {
    id: root
    width: Screen.width
    height: Screen.height
    property int stage

    // 渐变背景
    gradient: Gradient {
        GradientStop { position: 0.0; color: "#0d47a1" }
        GradientStop { position: 0.5; color: "#1565c0" }
        GradientStop { position: 1.0; color: "#0d47a1" }
    }

    onStageChanged: {
        if (stage == 2) {
            introAnimation.running = true;
        }
    }

    Item {
        id: content
        anchors.fill: parent
        opacity: 0

        // Logo 区域（带缩放动画）
        Item {
            id: logoBox
            anchors.centerIn: parent
            anchors.verticalCenterOffset: -80
            width: 180
            height: 140

            Image {
                id: logo
                anchors.centerIn: parent
                width: 160
                height: 120
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                source: "images/logo.png"
                visible: status === Image.Ready
                scale: 0.6
                transformOrigin: Item.Center
                ScaleAnimator on scale {
                    from: 0.6
                    to: 1
                    duration: 600
                    easing.type: Easing.OutBack
                    running: introAnimation.running && logo.status === Image.Ready
                }
            }
            Image {
                id: logoSvg
                anchors.centerIn: parent
                width: 160
                height: 120
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                source: "images/logo.svg"
                visible: logo.status !== Image.Ready && status === Image.Ready
                scale: 0.6
                transformOrigin: Item.Center
                ScaleAnimator on scale {
                    from: 0.6
                    to: 1
                    duration: 600
                    easing.type: Easing.OutBack
                    running: introAnimation.running && logoSvg.status === Image.Ready
                }
            }
        }

        // 主标语（随 content 淡入）
        Text {
            id: slogan
            anchors {
                top: logoBox.bottom
                horizontalCenter: parent.horizontalCenter
                topMargin: 24
            }
            text: "统御至诚"
            color: "#ffffff"
            font.pixelSize: 32
            font.bold: true
        }

        // 副标题
        Text {
            id: systemName
            anchors {
                top: slogan.bottom
                horizontalCenter: parent.horizontalCenter
                topMargin: 8
            }
            text: "统御至诚云桌面"
            color: "rgba(255,255,255,0.9)"
            font.pixelSize: 16
        }

        // 旋转加载指示器
        Item {
            id: busyIndicator
            y: parent.height - 140
            width: 56
            height: 56
            anchors.horizontalCenter: parent.horizontalCenter

            Image {
                id: busyImg
                anchors.centerIn: parent
                width: 48
                height: 48
                asynchronous: true
                source: "images/busywidget.svgz"
                visible: status === Image.Ready
                RotationAnimator on rotation {
                    from: 0
                    to: 360
                    duration: 1800
                    loops: Animation.Infinite
                    running: true
                }
            }
            Rectangle {
                anchors.centerIn: parent
                width: 40
                height: 40
                radius: 20
                color: "transparent"
                border.width: 3
                border.color: "rgba(255,255,255,0.5)"
                visible: busyImg.status !== Image.Ready
                RotationAnimator on rotation {
                    from: 0
                    to: 360
                    duration: 1200
                    loops: Animation.Infinite
                    running: true
                }
            }
        }

        // 底部品牌
        Row {
            spacing: 10
            anchors {
                bottom: parent.bottom
                horizontalCenter: parent.horizontalCenter
                bottomMargin: 28
            }
            Text {
                color: "rgba(255,255,255,0.85)"
                text: "统御至诚"
                font.pixelSize: 13
                anchors.verticalCenter: parent.verticalCenter
            }
            Image {
                id: bottomLogo
                width: 22
                height: 22
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                source: "images/logo.png"
                visible: status === Image.Ready
            }
            Image {
                id: bottomLogoSvg
                width: 22
                height: 22
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                source: "images/logo.svg"
                visible: bottomLogo.status !== Image.Ready && status === Image.Ready
            }
        }
    }

    OpacityAnimator {
        id: introAnimation
        running: false
        target: content
        from: 0
        to: 1
        duration: 700
        easing.type: Easing.InOutQuad
    }
}
