"""Entry visualization commands, with independent current-artifact and run state."""

from __future__ import annotations

import hashlib
from typing import Any

from testing_agent.core.errors import AppError, ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.core.sid import new_id
from testing_agent.domain.case_visualization.contract import (
    TASK_TYPE,
    canonical,
    freeze_input,
    validate_artifact,
)
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.case_visualization import (
    TestOrderEntryVisualization,
    TestOrderVisualizationBatch,
)
from testing_agent.models.test_order import TestOrder
from testing_agent.repositories.auxiliary_execution import lock_or_create_stage
from testing_agent.repositories.case_visualization import CaseVisualizationRepository
from testing_agent.services.auxiliary_execution import dispatch_auxiliary_execution
from testing_agent.services.auxiliary_request import find_replay, request_signature
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.test_order import TestOrderService


def run_summary(attempt: AiGenerationAttempt | None) -> dict[str, Any] | None:
    if attempt is None:
        return None
    context = attempt.output_context_json or {}
    return {
        "runId": attempt.execution_id,
        "status": attempt.status,
        "artifactStatus": context.get("artifactStatus"),
        "errorMessage": attempt.error_message,
    }


class TestOrderCaseVisualizationService:
    def __init__(self, repository: CaseVisualizationRepository, orders: TestOrderService) -> None:
        self.repository, self.orders = repository, orders
        self.session = repository.session

    async def get(self, actor: str, order_id: str, entry_id: str) -> dict[str, Any]:
        await self.orders.get_accessible_entity(actor, order_id, action="read")
        return await self._view(order_id, entry_id, content=True)

    async def lookup(self, actor: str, order_id: str, entry_ids: list[str]) -> dict[str, Any]:
        await self.orders.get_accessible_entity(actor, order_id, action="read")
        entries = await self.repository.entries(order_id, entry_ids)
        bindings = {
            x.entry_id: x for x in await self.repository.bindings([e.entry_id for e in entries])
        }
        rows = await self.repository.summary_attempts(
            [x.task_id for x in bindings.values()],
            [x.effective_attempt_id for x in bindings.values() if x.effective_attempt_id],
        )
        attempts = {attempt.id: attempt for _, attempt in rows}
        latest: dict[str, AiGenerationAttempt] = {}
        for task_id, attempt in rows:
            if task_id not in latest or attempt.attempt_no > latest[task_id].attempt_no:
                latest[task_id] = attempt
        items = []
        for entry in entries:
            binding = bindings.get(entry.entry_id)
            result: dict[str, Any] = {
                "executionEntryId": entry.entry_id,
                "snapshotHash": None,
                "effectiveArtifact": None,
                "latestRun": None,
            }
            try:
                frozen = freeze_input(entry.entry_id, entry.snapshot_json)
                result["snapshotHash"] = frozen["snapshotHash"]
            except ValueError as exc:
                result["unavailableReason"] = str(exc)
                items.append(result)
                continue
            if binding:
                result["latestRun"] = run_summary(latest.get(binding.task_id))
                effective = attempts.get(binding.effective_attempt_id or "")
                context = (effective.output_context_json or {}) if effective else {}
                if (
                    effective
                    and effective.status == "success"
                    and effective.invalidated_at is None
                    and binding.effective_snapshot_hash == frozen["snapshotHash"]
                    and context.get("schemaVersion") == "1.0"
                    and context.get("artifactStatus") in {"ready", "partial"}
                ):
                    result["effectiveArtifact"] = {
                        "artifactId": effective.id,
                        "runId": effective.execution_id,
                        "schemaVersion": "1.0",
                        "status": context["artifactStatus"],
                        "content": None,
                    }
            items.append(result)
        return {"items": items, "total": len(items)}

    async def _view(self, order_id: str, entry_id: str, *, content: bool) -> dict[str, Any]:
        entry = await self.repository.entry(order_id, entry_id)
        if entry is None:
            raise ErrNotFound()
        result: dict[str, Any] = {
            "executionEntryId": entry_id,
            "snapshotHash": None,
            "effectiveArtifact": None,
            "latestRun": None,
            "unavailableReason": None,
        }
        try:
            frozen = freeze_input(entry_id, entry.snapshot_json)
        except ValueError as exc:
            result["unavailableReason"] = str(exc)
            return result
        result["snapshotHash"] = frozen["snapshotHash"]
        binding = await self.repository.binding(entry_id)
        if binding is None:
            return result
        latest = await self.repository.latest(binding.task_id)
        result["latestRun"] = run_summary(latest)
        if latest and (latest.output_context_json or {}).get("artifactStatus") == "unsupported":
            try:
                unsupported = validate_artifact(frozen, latest.output_content or "")
                result["unavailableReason"] = "；".join(
                    x["reason"] for x in unsupported["limitations"]
                )
            except (ValueError, TypeError, RecursionError):
                pass
        if (
            binding.effective_attempt_id
            and binding.effective_snapshot_hash == frozen["snapshotHash"]
        ):
            attempt = await self.repository.attempt(binding.effective_attempt_id)
            if attempt and attempt.status == "success" and attempt.invalidated_at is None:
                source = (attempt.input_snapshot_json or {}).get("source", {})
                try:
                    if source.get("taskId") != binding.task_id or source.get("entryId") != entry_id:
                        raise ValueError("产物来源不匹配")
                    artifact = validate_artifact(frozen, attempt.output_content or "")
                    if artifact["status"] in {"ready", "partial"}:
                        result["effectiveArtifact"] = {
                            "artifactId": attempt.id,
                            "runId": attempt.execution_id,
                            "schemaVersion": artifact["schemaVersion"],
                            "status": artifact["status"],
                            "content": artifact if content else None,
                        }
                except (ValueError, TypeError, RecursionError):
                    result["unavailableReason"] = "图解版本或内容不可用，请重新生成"
        elif binding.effective_attempt_id:
            result["unavailableReason"] = "图解已过期，请重新生成"
        return result

    async def _locked_order(self, actor: str, order_id: str, connection: str) -> TestOrder:
        await self.orders.get_accessible_entity(actor, order_id, action="execute")
        # End the initial read snapshot before waiting on the owning order lock.
        await self.session.commit()
        order = await self.orders.repository.get_order_for_update(order_id)
        if order is None:
            raise ErrNotFound()
        await self.orders.get_accessible_entity(actor, order_id, action="execute")
        await require_personal_connection(self.session, actor, "llm", connection, order.project_id)
        return order

    async def dispatch(
        self,
        actor: str,
        order_id: str,
        entry_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        order = await self._locked_order(actor, order_id, body["connection_id"])
        receipt = await self._dispatch(actor, order, entry_id, body)
        await self.session.commit()
        return receipt

    async def _dispatch(
        self,
        actor: str,
        order: TestOrder,
        entry_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        entry = await self.repository.entry(order.order_id, entry_id, lock=True)
        if entry is None or entry.case_type != "function":
            raise ErrNotFound()
        try:
            frozen = freeze_input(entry_id, entry.snapshot_json)
        except ValueError as exc:
            raise dynamic_error(ErrBadRequest, str(exc)) from exc
        connection = body["connection_id"]
        mode = body.get("mode", "generate")
        signature = request_signature(
            TASK_TYPE,
            {
                "entryId": entry_id,
                "snapshotHash": frozen["snapshotHash"],
                "connectionId": connection,
                "mode": mode,
            },
        )
        request_id = hashlib.sha256(
            f"visualization:{actor}:{body['request_id']}".encode()
        ).hexdigest()
        binding = await self.repository.binding(entry_id)
        task = await self.repository.task(binding.task_id) if binding else None
        if binding and (
            task is None or task.task_type != TASK_TYPE or task.order_id != order.order_id
        ):
            raise ErrNotFound()
        if task:
            replay = await find_replay(
                self.session, task=task, actor_id=actor, request_id=request_id, signature=signature
            )
            if replay:
                return {"entryId": entry_id, "disposition": "queued", "runId": replay.execution_id}
            stage = await lock_or_create_stage(self.session, task.task_id)
            if stage.active_attempt_id:
                active = await self.repository.attempt(stage.active_attempt_id)
                return {
                    "entryId": entry_id,
                    "disposition": "existing_active",
                    "runId": active.execution_id if active else None,
                }
            if mode == "generate":
                view = await self._view(order.order_id, entry_id, content=False)
                if view["effectiveArtifact"]:
                    return {
                        "entryId": entry_id,
                        "disposition": "skipped_available",
                        "runId": view["effectiveArtifact"]["runId"],
                    }
        else:
            task = AiGenerateTask(
                task_id=new_id(),
                task_type=TASK_TYPE,
                name="执行条目可视化",
                project_id=order.project_id,
                sprint_id=order.sprint_id,
                requirement_id="",
                order_id=order.order_id,
                execution_entry_id=entry_id,
                creator_user_id=actor,
                source_type=TASK_TYPE,
                source_content="",
                instruction="",
            )
            self.session.add(task)
            await self.session.flush()
        attempt, _ = await dispatch_auxiliary_execution(
            self.session,
            task=task,
            actor_id=actor,
            request_id=request_id,
            execution_id=new_id(),
            connection_id=connection,
            source={
                "taskType": TASK_TYPE,
                "orderId": order.order_id,
                "entryId": entry_id,
                "snapshotHash": frozen["snapshotHash"],
            },
            config={"visualizationInput": frozen},
            request_signature=signature,
        )
        if binding is None:
            self.session.add(TestOrderEntryVisualization(entry_id=entry_id, task_id=task.task_id))
        await self.session.flush()
        return {"entryId": entry_id, "disposition": "queued", "runId": attempt.execution_id}

    async def batch_dispatch(
        self,
        actor: str,
        order_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        order = await self._locked_order(actor, order_id, body["connection_id"])
        signature = hashlib.sha256(canonical(body).encode()).hexdigest()
        batch = await self.repository.batch_replay(actor, body["request_id"])
        if batch:
            if batch.order_id != order_id or batch.signature != signature:
                raise dynamic_error(ErrBadRequest, "请求标识已用于其他输入")
        else:
            items = []
            for entry_id in body["entry_ids"]:
                try:
                    async with self.session.begin_nested():
                        receipt = await self._dispatch(
                            actor,
                            order,
                            entry_id,
                            {
                                "request_id": hashlib.sha256(
                                    f"batch:{body['request_id']}:{entry_id}".encode()
                                ).hexdigest(),
                                "connection_id": body["connection_id"],
                                "mode": "generate",
                            },
                        )
                    items.append(receipt)
                except AppError:
                    items.append(
                        {
                            "entryId": entry_id,
                            "disposition": "rejected",
                            "errorMessage": "条目不可用、无权访问或内容超限",
                        }
                    )
            batch = TestOrderVisualizationBatch(
                batch_id=new_id(),
                order_id=order_id,
                actor_id=actor,
                request_id=body["request_id"],
                signature=signature,
                items=items,
            )
            self.session.add(batch)
        batch_id = batch.batch_id
        # One atomic receipt: a transport replay sees all original dispositions or none.
        await self.session.commit()
        return await self.get_batch(actor, order_id, batch_id)

    async def get_batch(self, actor: str, order_id: str, batch_id: str) -> dict[str, Any]:
        await self.orders.get_accessible_entity(actor, order_id, action="read")
        batch = await self.repository.batch(batch_id, order_id)
        if batch is None:
            raise ErrNotFound()
        ids = [item["entryId"] for item in batch.items]
        entries = {e.entry_id for e in await self.repository.entries(order_id, ids)}
        bindings = {x.entry_id: x for x in await self.repository.bindings(list(entries))}
        rows = await self.repository.summary_attempts(
            [x.task_id for x in bindings.values()],
            [],
            [item["runId"] for item in batch.items if item.get("runId")],
        )
        runs = {(task_id, attempt.execution_id): attempt for task_id, attempt in rows}
        items: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        for original in batch.items:
            item = dict(original)
            if item["entryId"] not in entries:
                item = {
                    "entryId": item["entryId"],
                    "disposition": "rejected",
                    "errorMessage": "条目已不可用",
                }
            elif item.get("runId"):
                binding = bindings.get(item["entryId"])
                run = runs.get((binding.task_id, item["runId"])) if binding else None
                item["run"] = run_summary(run)
            state = item["disposition"]
            if state in {"queued", "existing_active"} and item.get("run"):
                state = item["run"].get("artifactStatus") or item["run"]["status"]
            counts[state] = counts.get(state, 0) + 1
            items.append(item)
        return {"batchId": batch_id, "items": items, "total": len(items), "counts": counts}
