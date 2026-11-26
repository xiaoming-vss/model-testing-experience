from testing_agent_integration_worker.domain.execution import Execution


class JobHandler:
    def __init__(self, workflow):
        self.workflow = workflow

    async def handle(self, execution: Execution) -> None:
        await self.workflow.run(execution)
