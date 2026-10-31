"""按步骤解析环境变量，并把后置提取的结果写回环境。"""

from __future__ import annotations

import asyncio
from typing import Any


class ResolvedVariables(dict[str, str]):
    """一次解析得到的取值，同时携带哪些变量属于私密变量。"""

    def __init__(
        self, values: dict[str, str], secret_names: list[str] | None = None
    ) -> None:
        super().__init__(values)
        self.secret_names = set(secret_names or [])


class StepVariableResolver:
    """通过控制面内部接口读写本次运行环境的当前取值。"""

    def __init__(self, client: Any, task_id: str, run_id: str) -> None:
        self.client = client
        self.task_id = task_id
        self.run_id = run_id

    async def resolve(self, names: list[str]) -> ResolvedVariables:
        if not names:
            return ResolvedVariables({})
        payload = await asyncio.to_thread(
            self.client.resolve_ui_run_variables, self.task_id, self.run_id, names
        )
        values = {
            str(key): "" if value is None else str(value)
            for key, value in (payload.get("values") or {}).items()
        }
        missing = [str(name) for name in payload.get("missing") or []]
        if missing:
            raise ValueError("环境变量不存在：" + "、".join(missing))
        secret_names = [str(name) for name in payload.get("secretNames") or []]
        return ResolvedVariables(values, secret_names)

    async def write(self, name: str, value: str, order_no: int | None = None) -> None:
        """把一个提取结果立即写回环境，失败直接抛出以让步骤失败。"""
        payload = await asyncio.to_thread(
            self.client.write_ui_run_variables,
            self.task_id,
            self.run_id,
            [{"name": name, "value": value, "orderNo": order_no}],
        )
        for result in payload.get("results") or []:
            if isinstance(result, dict) and result.get("success") is False:
                raise ValueError(f"变量写回失败：{name}")
