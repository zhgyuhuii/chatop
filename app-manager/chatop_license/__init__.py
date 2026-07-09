"""chatop 序列号激活：纯标准库，随 app_manager.py 一起进镜像。

对外只暴露 gate：其余模块是实现细节。
    from chatop_license import gate
    gate.state()            -> "off" | "needs_activation" | "expired" | "active"
    gate.activate(serial)   -> (ok: bool, err_code: int)

设计真源：docs/superpowers/specs/2026-07-09-serial-activation-design.md
"""
