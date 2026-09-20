"""测试单状态的推导规则。

与迭代状态同样，测试单状态是条目结果的函数，不是人工关闭事件：条目全部到达终态
即为已完成，一条都没有结果即为未开始，其余为执行中。
"""

from __future__ import annotations

from testing_agent.core.enums import TestOrderStatus


def derive_test_order_status(total: int, executed: int) -> str:
    if total <= 0 or executed <= 0:
        return TestOrderStatus.PENDING.value
    if executed >= total:
        return TestOrderStatus.COMPLETED.value
    return TestOrderStatus.IN_PROGRESS.value
