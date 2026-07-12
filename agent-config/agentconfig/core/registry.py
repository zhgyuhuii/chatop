# -*- coding: utf-8 -*-
"""适配器注册表。station 路由按 agent_id 分发到对应适配器。

惰性构造：适配器实例可能读磁盘/触发探测，故按需构造并缓存。测试可注入替身。
"""
from __future__ import annotations

from typing import Callable, Optional

from .adapter import AgentAdapter

# {id: 构造函数}
_FACTORIES: dict[str, Callable[[], AgentAdapter]] = {}
_CACHE: dict[str, AgentAdapter] = {}


def register(agent_id: str, factory: Callable[[], AgentAdapter]) -> None:
    _FACTORIES[agent_id] = factory
    _CACHE.pop(agent_id, None)


def get(agent_id: str) -> AgentAdapter:
    if agent_id not in _FACTORIES:
        raise KeyError(f"no adapter registered for {agent_id!r}")
    if agent_id not in _CACHE:
        _CACHE[agent_id] = _FACTORIES[agent_id]()
    return _CACHE[agent_id]


def ids() -> list[str]:
    return list(_FACTORIES.keys())


def reset() -> None:
    """测试用：清空缓存（不清工厂）。"""
    _CACHE.clear()


def install_defaults(*, home: Optional[str] = None) -> None:
    """注册内置适配器。延迟 import 避免循环依赖，且缺依赖时不整体崩。"""
    def _openclaw():
        from ..adapters.openclaw_adapter import OpenClawAdapter
        return OpenClawAdapter(home=home)

    def _hermes():
        from ..adapters.hermes_adapter import HermesAdapter
        return HermesAdapter(home=home)

    register("openclaw", _openclaw)
    register("hermes", _hermes)
