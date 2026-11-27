"""Backend-neutral agent contract shared by the Nanobot and Pi adapters.

业务层只依赖这里的 `Agent` 协议与 `AgentResult`，不直接引用任何后端 SDK。
两个适配器对非正常结束一律抛 `AgentOutputError`，所以成功返回的结果一定是完整的。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from testing_agent_ai_worker.core.errors import AgentOutputError

LOGGER = logging.getLogger(__name__)

# 每个适配器只在这一种结束原因下返回结果，其余全部抛错。
FinishReason = Literal["stop"]

_OUTPUT_INCOMPLETE_MESSAGES = {
    "error": "模型调用出错，请检查模型服务或授权后重试",
    "tool_error": "模型工具调用出错，请重试",
    "length": "模型输出被截断，请调整输出限制或缩小生成范围后重试",
    "max_tokens": "模型输出被截断，请调整输出限制或缩小生成范围后重试",
    "max_output_tokens": "模型输出被截断，请调整输出限制或缩小生成范围后重试",
    "max_iterations": "模型在限定轮次内没有完成生成，请缩小任务范围或简化指令后重试",
    "empty_final_response": "模型没有返回内容，请重试",
    "aborted": "模型调用被中止",
    "cancelled": "模型调用已取消",
    "canceled": "模型调用已取消",
}
_OUTPUT_INCOMPLETE_MESSAGE = "模型没有正常完成生成，请重试；持续出现时请检查模型服务配置"


def incomplete_output_error(reason: object) -> AgentOutputError:
    """Map how a backend ended to a fixed user message; the reason itself only goes to the log."""
    key = reason if isinstance(reason, str) else ""
    if key not in _OUTPUT_INCOMPLETE_MESSAGES:
        LOGGER.warning("agent ended with an unknown reason: %s", key[:64] or "<empty>")
    return AgentOutputError(_OUTPUT_INCOMPLETE_MESSAGES.get(key, _OUTPUT_INCOMPLETE_MESSAGE))


@dataclass(slots=True)
class AgentResult:
    """一次生成调用归一化后的结果。"""

    content: str
    finish_reason: FinishReason
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
