#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""OpenClaw 配置器 — 二维码捕获与渲染模块。

设计（对齐 spec）：三策略择优、带保底，不预设 openclaw 输出格式：
  ① 原始串  : 若拿到二维码底层字符串/URL，且本机有 qrcode 库 → 编码成矩阵
  ② ASCII 回解: 解析终端打印的 ASCII 二维码块（██ 或 ▀▄ 半块）→ 0/1 矩阵
  ③ 保底    : 前两者都拿不到 → 返回 None，由调用方提示「在终端扫码」

渲染用 Tk Canvas 画黑白方格，不依赖 qrcode/PIL（tkinter 在渲染函数内惰性导入，
保证本模块在无 GUI 环境也能被单元测试）。
"""

# —— 字符集：判定某个字符是「暗模块（黑）」还是「亮模块（白）」——
_DARK_CHARS = set("█▓▒░■#*@Xx1")   # 常见二维码「黑」用块字符
_HALF_UPPER = "▀"                   # 上半黑、下半白
_HALF_LOWER = "▄"                   # 上半白、下半黑
_HALF_FULL = "█"                    # 上下都黑
_HALF_CHARS = set(_HALF_UPPER + _HALF_LOWER)


def _strip_blank_border(lines):
    """去掉四周纯空白的行/列，返回裁剪后的行列表。"""
    rows = [ln.rstrip("\n") for ln in lines]
    # 去掉首尾全空行
    while rows and rows[0].strip() == "":
        rows.pop(0)
    while rows and rows[-1].strip() == "":
        rows.pop()
    if not rows:
        return []
    # 去掉左右公共空白列
    width = max(len(r) for r in rows)
    rows = [r.ljust(width) for r in rows]
    left = 0
    while left < width and all(r[left] == " " for r in rows):
        left += 1
    right = width
    while right > left and all(r[right - 1] == " " for r in rows):
        right -= 1
    return [r[left:right] for r in rows]


def _dark(ch):
    return ch in _DARK_CHARS


def _collapse_horizontal_doubling(matrix):
    """qrcode-terminal 常把每模块横向渲染成 2 个字符宽。若发现每一对相邻列
    完全相等，则横向减半，得到真实模块矩阵。"""
    if not matrix or not matrix[0]:
        return matrix
    w = len(matrix[0])
    if w % 2 != 0:
        return matrix
    for row in matrix:
        for i in range(0, w, 2):
            if row[i] != row[i + 1]:
                return matrix  # 不是整齐的横向 2 倍，放弃减半
    return [[row[i] for i in range(0, w, 2)] for row in matrix]


def parse_ascii_qr(text):
    """把终端 ASCII 二维码块解析成 0/1 矩阵（1=黑）。无法解析返回 None。

    支持两种编码：
      - 半块模式（含 ▀/▄）：每字符编码上下两个模块，1 文本行 = 2 模块行。
      - 全块模式（██/空格）：暗=块字符，亮=空格；自动横向减半。
    """
    if not text or not text.strip():
        return None
    rows = _strip_blank_border(text.splitlines())
    if not rows:
        return None

    joined = "".join(rows)
    is_half = any(c in _HALF_CHARS for c in joined)

    matrix = []
    if is_half:
        width = max(len(r) for r in rows)
        for line in rows:
            line = line.ljust(width)
            top, bottom = [], []
            for ch in line:
                if ch == _HALF_FULL:
                    top.append(1); bottom.append(1)
                elif ch == _HALF_UPPER:
                    top.append(1); bottom.append(0)
                elif ch == _HALF_LOWER:
                    top.append(0); bottom.append(1)
                else:  # 空格或其它 = 上下都亮
                    top.append(0); bottom.append(0)
            matrix.append(top)
            matrix.append(bottom)
        # 半块模式最后一行可能多出一行纯 0（原始为奇数模块行时的补齐），去掉尾部全 0 行
        while len(matrix) > 1 and all(v == 0 for v in matrix[-1]):
            matrix.pop()
    else:
        width = max(len(r) for r in rows)
        for line in rows:
            line = line.ljust(width)
            matrix.append([1 if _dark(ch) else 0 for ch in line])
        matrix = _collapse_horizontal_doubling(matrix)

    # 基本合法性：非空、近似方阵（二维码是正方形，容忍少量误差）
    if not matrix or not matrix[0]:
        return None
    h, w = len(matrix), len(matrix[0])
    if h < 9 or w < 9:            # 最小二维码是 21x21，低于 9 基本是噪声
        return None
    if abs(h - w) > max(h, w) * 0.25:
        return None
    return matrix


def encode_to_matrix(data):
    """策略①：有 qrcode 库时把原始串/URL 编码成 0/1 矩阵；无库返回 None。"""
    if not data:
        return None
    try:
        import qrcode  # 运行时探测，缺库即降级
    except Exception:
        return None
    try:
        qr = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(data)
        qr.make(fit=True)
        return [[1 if cell else 0 for cell in row] for row in qr.get_matrix()]
    except Exception:
        return None


def capture(handoff):
    """从交接数据里择优取二维码矩阵。
    handoff: dict，可能含 {"qr_raw": "...", "qr_ascii": "..."}。
    返回 (source, matrix)：source ∈ {"raw","ascii",None}；拿不到则 (None, None)。
    """
    handoff = handoff or {}
    raw = handoff.get("qr_raw")
    if raw:
        m = encode_to_matrix(raw)
        if m:
            return "raw", m
    ascii_block = handoff.get("qr_ascii")
    if ascii_block:
        m = parse_ascii_qr(ascii_block)
        if m:
            return "ascii", m
    return None, None


def render_matrix_tk(parent, matrix, box=6, quiet=4, dark="#000000", light="#ffffff"):
    """在 Tk 父容器里用 Canvas 画二维码方格。返回 Canvas。
    box: 每模块像素；quiet: 四周静默区模块数。tkinter 惰性导入。"""
    import tkinter as tk  # noqa: 惰性导入，保证无 GUI 环境可 import 本模块
    h = len(matrix)
    w = len(matrix[0]) if h else 0
    size_w = (w + quiet * 2) * box
    size_h = (h + quiet * 2) * box
    cv = tk.Canvas(parent, width=size_w, height=size_h, highlightthickness=0, bg=light)
    for y, row in enumerate(matrix):
        for x, cell in enumerate(row):
            if cell:
                x0 = (x + quiet) * box
                y0 = (y + quiet) * box
                cv.create_rectangle(x0, y0, x0 + box, y0 + box, fill=dark, outline=dark)
    return cv


def matrix_to_ascii(matrix, dark="██", light="  "):
    """把矩阵转回 ASCII（调试/测试用）。"""
    return "\n".join("".join(dark if c else light for c in row) for row in matrix)
