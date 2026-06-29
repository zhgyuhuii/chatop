# 统御至诚 - 自定义开机动画

完整自定义开机动画，包含：
- **渐变背景**：蓝色渐变（#0d47a1 → #1565c0）
- **Logo 缩放**：从 0.6 弹性放大到 1（Easing.OutBack）
- **旋转加载**：busywidget.svgz 持续旋转
- **整体淡入**：700ms 淡入动画

## 目录结构

```
custom-splash/
├── metadata.desktop          # 主题元数据（一般无需修改）
├── contents/
│   └── splash/
│       ├── Splash.qml        # 动画逻辑（可修改布局、颜色）
│       └── images/           # 图片资源
│           ├── splash.png   # 主图（推荐 512x512 或更大）
│           ├── splash.gif   # 或使用 GIF 实现动画
│           └── logo.png     # 备用图（无 splash 时使用）
└── README.md
```

## 制作步骤

### 1. 准备图片

- **splash.png**：静态开机图，推荐 512×512 或 1024×1024，PNG 透明背景
- **splash.gif**：动态开机图，可选，会覆盖 splash.png
- 若两者都没有，将使用项目根目录的 `logo.png`

### 2. 修改样式（可选）

编辑 `contents/splash/Splash.qml` 可调整：

- **渐变背景**：`GradientStop` 的 `color` 和 `position`
- **Logo 缩放**：`ScaleAnimator` 的 `from`、`to`、`duration`、`easing.type`
- **旋转速度**：`RotationAnimator` 的 `duration`（越小转得越快）
- **淡入时长**：`introAnimation` 的 `duration`

### 3. 构建与生效

```bash
docker compose build --no-cache
```

首次启动新容器时，会自动应用此开机动画。

## ksplashqml 崩溃排查

若仍崩溃，编辑 `custom-cont-init.d/92-themes-and-openclaw.sh`，将 `Theme=org.webtop.custom-splash` 改为 `Theme=org.kde.breeze.desktop` 使用默认 Breeze。

## 技术说明

- 基于 Plasma Look and Feel 包，仅包含 splash 部分
- QML 使用 `stage` 属性（1–5）表示加载进度
- 安装路径：`/usr/share/plasma/look-and-feel/org.webtop.custom-splash/`
- 配置：`~/.config/ksplashrc` 中 `[KSplash] Theme=org.webtop.custom-splash`
