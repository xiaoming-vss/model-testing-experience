from testing_agent_integration_worker.domain.execution import Execution


class JobHandler:
    def __init__(self, workflow):
        self.workflow = workflow

    async def handle(self, execution: Execution) -> None:
        # Claim schema and server capability intersection guarantee these two workflows.
        if execution.claim.protocol_version != 1 or execution.claim.task_type not in {
            "zentao_bug_sync",
            "zentao_bug_fields_update",
        }:
            return
        await self.workflow.run(execution)
