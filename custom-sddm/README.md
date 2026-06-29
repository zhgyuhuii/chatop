# 统御至诚 - SDDM 登录主题

自定义 SDDM 登录界面，含 Logo、统御至诚、系统名称。

## 配置 (theme.conf)

| 键 | 默认值 | 说明 |
|----|--------|------|
| SystemName | 统御至诚云桌面 | 系统名称 |
| Slogan | 统御至诚 | 主标语 |
| LogoPath | images/logo.png | Logo 路径 |

## 安装

构建时由 Dockerfile 自动安装到 `/usr/share/sddm/themes/tongyu-zhicheng/`，并设置默认主题。

## 预览

```bash
sddm-greeter --test-mode --theme /usr/share/sddm/themes/tongyu-zhicheng
```
