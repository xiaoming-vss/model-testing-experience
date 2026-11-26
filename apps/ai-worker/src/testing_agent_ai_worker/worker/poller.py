"""Single-iteration poller wrapper.

调用链路：
- `run_worker_loop/_run_worker_iteration -> TaskPoller.poll`
- `TaskPoller -> TaskSource.poll_task`
"""

from __future__ import annotations

from testing_agent_ai_worker.models.task import Task
from testing_agent_ai_worker.platform.task_source import TaskSource


class TaskPoller:
    """单轮任务获取门面。"""

    def __init__(self, task_source: TaskSource) -> None:
        self.task_source = task_source

    def poll(self) -> Task | None:
        """轮询获取一个任务。"""

        return self.task_source.poll_task()
