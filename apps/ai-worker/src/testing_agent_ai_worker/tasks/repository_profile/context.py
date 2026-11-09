"""Build the fixed context for one repository profile call."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from testing_agent_ai_worker.agent.prompt import STRUCTURED_REQUIREMENT_INPUT_INSTRUCTION
from testing_agent_ai_worker.models.task import Task
from testing_agent_ai_worker.requirement_artifacts import requirement_content
from testing_agent_ai_worker.tasks.repository_profile.workspace import ProfileWorkspace


@dataclass(slots=True)
class ProfileContext:
    text: str
    manifest: dict[str, Any]


def build_profile_context(task: Task, workspace: ProfileWorkspace) -> ProfileContext:
    """Describe the selected understanding and the readable repository roots."""

    parts: list[str] = ["# 需求理解记录"]
    if task.requirement_input is None or not task.requirement_input.document_content.strip():
        raise ValueError("任务快照缺少已审核需求理解记录")
    parts.append(STRUCTURED_REQUIREMENT_INPUT_INSTRUCTION)
    parts.append(requirement_content(task.requirement_input.document_content))

    parts.append("# 仓库画像任务")
    parts.append(
        "请判断下列每个可分析仓库对当前需求的粗粒度角色，并给出一句话职责。"
        "只做仓库级判断，不做文件级、接口级、调用链或风险分析。"
    )
    parts.append("# 可分析仓库")
    parts.append(json.dumps(workspace.manifest["repositories"], ensure_ascii=False, indent=2))
    if workspace.unavailable:
        parts.append("# 无法读取的仓库")
        parts.append(json.dumps(workspace.manifest["unavailable"], ensure_ascii=False, indent=2))
        parts.append(
            "这些仓库没有本次代码上下文，不要为它们输出 repositories 条目；"
            "Worker 会把它们补成 unknown。"
        )
    return ProfileContext(
        text="\n\n".join(part for part in parts if part), manifest=workspace.manifest
    )
