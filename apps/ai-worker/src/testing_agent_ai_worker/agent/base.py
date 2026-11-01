"""Backend-neutral agent contract shared by the Nanobot and Pi adapters.

业务层只依赖这里的 `Agent` 协议与 `AgentResult`，不直接引用任何后端 SDK。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class AgentResult:
    """一次生成调用归一化后的结果。"""

    content: str
    finish_reason: str
    usage: dict[str, float] = field(default_factory=dict)


class AgentConfigPath(str):
    """任务级配置路径，同时记录生成它的后端。

    配置文件内容保持各 SDK 的原生格式，`backend` 因此放在路径对象上，
    业务层仍可把它当作普通字符串路径使用。
    """

    backend: str

    def __new__(cls, path: str, backend: str) -> AgentConfigPath:
        instance = super().__new__(cls, path)
        instance.backend = backend
        return instance


@runtime_checkable
class Agent(Protocol):
    """每个执行底座都必须满足的最小契约。"""

    @classmethod
    def from_config(cls, *, config_path: str | None = None, workspace: str | None = None) -> Agent:
        """按任务级配置创建实例。"""

    async def __aenter__(self) -> Agent:
        """进入调用作用域。"""

    async def __aexit__(self, *exc_info: Any) -> bool:
        """离开调用作用域并回收资源。"""

    async def run(
        self, message: str, *, session_key: str, media: list[str] | None = None
    ) -> AgentResult:
        """执行一次生成并返回归一化结果。"""
