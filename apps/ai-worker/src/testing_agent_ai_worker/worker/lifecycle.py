"""Worker polling and heartbeat cadence helpers.

这里集中维护：
- 空闲时多久轮询一次
- heartbeat 间隔如何计算
"""

from __future__ import annotations


class WorkerLifecycle:
    """worker 的轮询与心跳节奏配置对象。"""

    def __init__(
        self,
        *,
        poll_interval_seconds: int,
        heartbeat_interval_seconds: int,
        run_once: bool,
    ) -> None:
        self.poll_interval_seconds = poll_interval_seconds
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.run_once = run_once

    def heartbeat_interval_for(self, lease_seconds: int) -> int:
        """计算 heartbeat 间隔：最多为租约的一半，漏掉一次仍来得及续租。

        显式配置的间隔是上限；未配置时只由租约决定。
        """

        half = max(1, lease_seconds // 2)
        if self.heartbeat_interval_seconds > 0:
            return min(self.heartbeat_interval_seconds, half)
        return half
