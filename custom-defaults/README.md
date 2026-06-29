# 构建时界面定制

将文件放入此目录，构建镜像时会打包进镜像。**首次启动容器**时，若 `/config` 为空，会自动复制到用户配置目录，实现界面预定制。

## 目录结构（对应 /config）

```
custom-defaults/
├── .config/                    # KDE/应用配置
│   ├── kdeglobals             # KDE 全局设置
│   ├── kwinrc                 # 窗口管理器
│   ├── plasma-org.kde.plasma.desktop-appletsrc  # 面板/任务栏布局
│   └── ...
├── .local/
│   └── share/
│       └── plasma/            # 主题、壁纸等
├── Desktop/                   # 桌面快捷方式
└── README.md
```

## 使用步骤

1. **准备配置**：在本地 KDE 中调整好界面（主题、任务栏、壁纸等）
2. **导出配置**：将 `~/.config`、`~/.local/share` 等目录中需要的文件复制到 `custom-defaults/` 对应路径
3. **构建镜像**：`docker compose build --no-cache`
4. **首次运行**：使用**新的空 volume** 启动，配置会自动应用

## 注意事项

- 仅当 `/config` **为空**时才会复制，已有数据的 volume 不会被覆盖
- 若要重新应用默认配置，需删除 volume 或使用新 volume
- 路径需与 `/config` 下结构一致（`custom-defaults/.config` → `/config/.config`）

## 主题类型与位置（KDE/Plasma）

构建时安装的主题类型不同，在系统设置中的位置也不同：

| 类型 | 来源 | 在系统设置中的位置 |
|------|------|-------------------|
| **KDE Look and Feel** | 根目录 `*-kde*.zip`（如 MacVentura、WhiteSur、Layan、Fluent 等） | **外观** → 全局外观 |
| **GTK 主题** | Orchis、Vimix、WhiteSur-gtk | **外观** → 应用程序风格 → 配置 GNOME/GTK 应用程序风格 |
| **图标主题** | Tela、WhiteSur-icon | **外观** → 图标 |

**KDE 主题**：将任意 `*-kde*.zip` 放入项目根目录，构建时会自动安装。

**图标主题**：在 `kdeglobals` 的 `[Icons] Theme=` 中设置（如 WhiteSur、Tela）。构建时已安装 WhiteSur、Tela 图标主题。

## 开机动画

自定义开机动画在 `custom-splash/` 目录，详见 `custom-splash/README.md`。构建时自动安装，首次启动通过 `ksplashrc` 应用。

## 常用配置文件

| 文件 | 说明 |
|------|------|
| `.config/kdeglobals` | 主题、字体、颜色 |
| `.config/kwinrc` | 窗口装饰、快捷键 |
| `.config/plasma-org.kde.plasma.desktop-appletsrc` | 面板、任务栏、部件 |
| `.config/plasmarc` | Plasma 通用设置 |
| `.config/kdeglobals` → `[KDE]` `SingleClick` | 单击/双击打开 |
