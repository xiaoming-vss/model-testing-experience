"""Bounded draft generation from approved test objects, including shared coverage."""

import asyncio
import json
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any
from uuid import uuid4

from testing_agent_ai_worker.traceable_test_points import validate_traceable_test_points

from .module_execution import ModuleProgress
from .validation import context, generate_validated


@dataclass(frozen=True)
class PointDraftGroup:
    label: str
    object_ids: tuple[str, ...]


def draft_groups(scope: dict[str, Any]) -> list[PointDraftGroup]:
    """Bound request fan-out without inventing modules or dropping unconfirmed objects."""
    objects = scope.get("testObjects", [])
    if len(objects) < 2:
        return []
    size = math.ceil(len(objects) / 3)
    groups = []
    for offset in range(0, len(objects), size):
        batch = objects[offset : offset + size]
        groups.append(
            PointDraftGroup(
                label=f"对象组 {len(groups) + 1}："
                + "、".join(row.get("name", row["id"]) for row in batch),
                object_ids=tuple(row["id"] for row in batch),
            )
        )
    groups.append(PointDraftGroup(label="跨组与公共规则", object_ids=()))
    return groups


def _check_group(value: dict[str, Any], index: int, groups: list[PointDraftGroup]) -> None:
    owners = {object_id: i for i, group in enumerate(groups) for object_id in group.object_ids}
    shared = len(groups) - 1
    if value["reviewStatus"] != "self_review_only" or value.get("reviewIssues"):
        raise ValueError("分组初稿须为 self_review_only，不提交独立审查意见")
    for collection in ("testPoints", "coverageGaps"):
        for entry in value[collection]:
            assigned = {owners[key] for key in entry["testObjectIds"]}
            owner = next(iter(assigned)) if len(assigned) == 1 else shared
            if owner != index:
                raise ValueError(
                    f"分组范围错误：{entry['id']} 不属于本组，请只返回指定对象或公共范围的条目"
                )


def merge_drafts(outputs: list[str], material: dict[str, Any], scope: dict[str, Any]) -> str:
    """Deduplicate exact content only; preserve semantic distinctions for global review."""
    result: dict[str, Any] = {
        "schemaVersion": "1.0",
        "artifactType": "traceable_test_points",
        "reviewStatus": "self_review_only",
        "testPoints": [],
        "coverageGaps": [],
    }
    for collection, prefix in (("testPoints", "tp"), ("coverageGaps", "gap")):
        seen = set()
        for output in outputs:
            for entry in json.loads(output)[collection]:
                content = {
                    key: sorted(value) if key.endswith("Ids") else value
                    for key, value in entry.items()
                    if key != "id"
                }
                signature = json.dumps(content, ensure_ascii=False, sort_keys=True)
                if signature in seen:
                    continue
                seen.add(signature)
                result[collection].append(
                    {**entry, "id": f"{prefix}-{len(result[collection]) + 1}"}
                )
    validate_traceable_test_points(result, material, scope)
    return json.dumps(result, ensure_ascii=False)


async def generate_point_drafts(
    *,
    prompt: str,
    material: dict[str, Any],
    scope: dict[str, Any],
    groups: list[PointDraftGroup],
    progress: ModuleProgress,
    generate: Callable[[str, str], Awaitable[Any]],
) -> str:
    """Generate at most two isolated groups concurrently, then merge before review."""
    slots = asyncio.Semaphore(2)
    dispatch = uuid4().hex
    execution = context.get()
    stopping = False
    plan = [{"group": i, "testObjectIds": list(group.object_ids)} for i, group in enumerate(groups)]

    async def run_group(index: int, group: PointDraftGroup) -> str:
        nonlocal stopping
        async with slots:
            if stopping:
                raise asyncio.CancelledError()
            token = None
            try:
                await progress.emit(index, "running")

                async def report(event: dict[str, Any]) -> None:
                    if event.get("status") == "repairing":
                        await progress.emit(
                            index, "repairing", repairAttempt=event["repairAttempt"]
                        )

                if execution:
                    token = context.set(replace(execution, report=report))
                group_prompt = (
                    prompt
                    + "\n\n【程序分派的测试点初稿分组】\n"
                    + json.dumps(
                        {
                            "group": index,
                            "assignedTestObjectIds": list(group.object_ids),
                            "groups": plan,
                            "sharedGroup": len(groups) - 1,
                        },
                        ensure_ascii=False,
                    )
                    + (
                        "\n先读取 references/parallel-generation.md（位于本次测试点技能目录）。"
                        "完整材料和范围分析均为冻结输入，仅在分派范围内生成，不再自主委派。"
                        "testObjectIds 全部属于同一对象组的条目由该组负责；跨不同对象组或无对象引用的条目由公共组负责。"
                        "依据事实保留真实关联，不通过删除或伪造引用绕过归属。"
                        "本组输出仍为完整 traceable_test_points JSON 外壳，只有本组条目，reviewStatus=self_review_only。"
                        "跨组及公共目标由公共组生成，已确认交互写测试点，确实未知才写覆盖缺口；不把分组边界本身当成业务缺口。"
                        "保留上游来源 ID；局部测试点和缺口 ID 由平台合并后统一编号。"
                    )
                )
                output = await generate_validated(
                    stage="traceable_case_names",
                    module=group.label,
                    batch=index + 1,
                    inputs=group_prompt,
                    material=material,
                    analysis=scope,
                    post_validate=lambda value: _check_group(value, index, groups),
                    generate=lambda text: generate(text, f"draft-{dispatch}-{index}"),
                )
                await progress.emit(
                    index, "completed", pointCount=len(json.loads(output)["testPoints"])
                )
                return output
            except asyncio.CancelledError:
                raise
            except Exception:
                stopping = True
                await progress.emit(index, "failed")
                raise
            finally:
                if token is not None:
                    context.reset(token)

    await progress.emit()
    tasks = [asyncio.create_task(run_group(i, group)) for i, group in enumerate(groups)]
    try:
        outputs = await asyncio.gather(*tasks)
        await progress.emit(status="merging")
        return merge_drafts(outputs, material, scope)
    except BaseException:
        stopping = True
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
