#!/usr/bin/env python3.11
"""归一化应用市场图标，保证在深色(#232834)和浅色(#f3f4f6)两种卡片底色上都看得见。

背景：
  - 新增的 13 个国产应用当初只塞了占位符（与 apps-icon.svg 字节相同的白色四方块），
    在浅色主题上是白底白图，等于没图标。
  - dreamm / moonlight / retroarch 的 SVG 没有 fill，默认渲染成黑色，在默认的深色卡片上隐形。
  - 回退图标 apps-icon.svg 自己也是纯白。

做法：
  - 有 simple-icons 官方字形的（qq、baidu-netdisk）直接用其 path + 官方品牌色。
  - 其余国产应用生成品牌色字标（圆角方块 + 白字），离线可用、彼此可区分、不碰商标图形。
  - 无 fill 的图标补一个中性色。
  - 所有颜色都做亮度钳制，保证相对亮度落在 [0.13, 0.38]，两种底色下对比度都 >= 2.0。

用法（simple-icons 仅在重新生成 qq/baidu-netdisk 字形时需要）：
    python3.11 normalize-icons.py [--simple-icons <解包后的 simple-icons 包目录>]

产物直接覆盖 icons/ 下的文件，是提交进仓库的资产。本脚本可重复运行。
"""
from __future__ import annotations

import argparse
import colorsys
import os
import pathlib

ICON_DIR = pathlib.Path(__file__).parent / "icons"
FALLBACK = pathlib.Path(__file__).parent / "apps-icon.svg"

DARK_CARD = "232834"
LIGHT_CARD = "f3f4f6"
LUM_MIN, LUM_MAX = 0.13, 0.38
NEUTRAL = "#7a828c"

# 只有字形、没有配色的图标：补中性色即可（图形本身是好的）
NO_FILL = {
    "dreamm": NEUTRAL,
    "moonlight": "#6ba4e7",
    "retroarch": NEUTRAL,
}

# simple-icons 里有官方字形的
SI_GLYPH = {
    "qq": ("tencentqq", "#1ebafc"),
    "baidu-netdisk": ("baidu", "#2932e1"),
}

# 其余国产应用：品牌色字标。CJK 单字比拉丁缩写更好认，市场里应用名本来也是中文。
LETTERMARK = {
    "dingtalk": ("钉", "#1677ff"),
    "feishu": ("飞", "#3370ff"),
    "tencent-meeting": ("会", "#0e5fff"),
    "qqmusic": ("音", "#31c27c"),
    "lingma": ("灵", "#ff6a00"),
    "todesk": ("TD", "#1e88e5"),
    "utools": ("uT", "#6c5ce7"),
    "motrix": ("MX", "#21b47c"),
    "codebuddy": ("CB", "#0d9488"),
    "qoder": ("QD", "#6e56cf"),
    "trae": ("TR", "#f0453a"),
}

FONT = "system-ui,-apple-system,'Noto Sans CJK SC','Microsoft YaHei',sans-serif"


def _srgb_to_lin(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex6: str) -> float:
    h = hex6.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * _srgb_to_lin(r) + 0.7152 * _srgb_to_lin(g) + 0.0722 * _srgb_to_lin(b)


def contrast(a: str, b: str) -> float:
    l1, l2 = luminance(a), luminance(b)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def clamp_lum(hex6: str) -> str:
    """保持色相饱和度，调整 HSL 明度，把相对亮度拉进 [LUM_MIN, LUM_MAX]。

    纯黑/纯白没有色相，会退化成中性灰——这正是我们要的（黑色品牌色如 IntelliJ 在深色卡片上没法用）。
    """
    h = hex6.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    if LUM_MIN <= luminance(hex6) <= LUM_MAX:
        return "#" + h.lower()
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    if sat == 0:  # 无色相，直接给中性色
        return NEUTRAL
    lo, hi = 0.0, 1.0
    for _ in range(40):  # 二分明度
        mid = (lo + hi) / 2
        rr, gg, bb = colorsys.hls_to_rgb(hue, mid, sat)
        cur = "#%02x%02x%02x" % (round(rr * 255), round(gg * 255), round(bb * 255))
        lum = luminance(cur)
        if lum < LUM_MIN:
            lo = mid
        elif lum > LUM_MAX:
            hi = mid
        else:
            return cur
    return NEUTRAL


def lettermark(text: str, color: str) -> str:
    size = 30 if len(text) == 1 else 23
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">\n'
        f'  <rect width="64" height="64" rx="14" fill="{color}"/>\n'
        f'  <text x="32" y="32" font-family="{FONT}" font-size="{size}" font-weight="600"'
        ' fill="#ffffff" text-anchor="middle" dominant-baseline="central">'
        f"{text}</text>\n"
        "</svg>\n"
    )


def si_glyph(pkg: pathlib.Path, slug: str, color: str) -> str:
    src = (pkg / "icons" / f"{slug}.svg").read_text(encoding="utf-8")
    start, end = src.index("<path"), src.rindex("</svg>")
    path = src[start:end]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="64" height="64"'
        f' fill="{color}">\n  {path}\n</svg>\n'
    )


def add_root_fill(svg: str, color: str) -> str:
    i = svg.index("<svg")
    j = svg.index(">", i)
    head = svg[i:j]
    if "fill=" in head:
        return svg
    return svg[:j] + f' fill="{color}"' + svg[j:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simple-icons", type=pathlib.Path, default=None)
    args = ap.parse_args()

    changed = []

    for app_id, (glyph, color) in LETTERMARK.items():
        (ICON_DIR / f"{app_id}.svg").write_text(lettermark(glyph, clamp_lum(color)), encoding="utf-8")
        changed.append(app_id)

    if args.simple_icons:
        for app_id, (slug, color) in SI_GLYPH.items():
            (ICON_DIR / f"{app_id}.svg").write_text(
                si_glyph(args.simple_icons, slug, clamp_lum(color)), encoding="utf-8"
            )
            changed.append(app_id)
    elif any(not (ICON_DIR / f"{a}.svg").exists() for a in SI_GLYPH):
        print("警告：缺 --simple-icons，qq / baidu-netdisk 字形未生成")

    for app_id, color in NO_FILL.items():
        p = ICON_DIR / f"{app_id}.svg"
        out = add_root_fill(p.read_text(encoding="utf-8"), clamp_lum(color))
        p.write_text(out, encoding="utf-8")
        changed.append(app_id)

    FALLBACK.write_text(
        FALLBACK.read_text(encoding="utf-8").replace('fill="#ffffff"', f'fill="{NEUTRAL}"'),
        encoding="utf-8",
    )
    changed.append("apps-icon.svg(回退)")

    print(f"已归一化 {len(changed)} 个图标")
    for c in sorted(changed):
        print("   ", c)
    print(f"\n中性色 {NEUTRAL}: vs深={contrast(NEUTRAL, DARK_CARD):.2f} vs浅={contrast(NEUTRAL, LIGHT_CARD):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
