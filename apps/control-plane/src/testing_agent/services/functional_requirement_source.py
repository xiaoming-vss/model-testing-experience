"""Freeze functional generation input from an approved requirement-understanding version."""

from typing import Any

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.requirement_artifacts import requirement_content
from testing_agent.repositories.generation_chain import GenerationChainRepository


async def functional_requirement_source(
    repository: GenerationChainRepository, requirement_id: str, version_id: str = ""
) -> dict[str, Any]:
    task = await repository.task(requirement_id, "requirement_analysis")
    version = None
    if task is not None:
        if version_id:
            version = await repository.version(task.task_id, version_id)
        else:
            version = await repository.latest_version(task.task_id, "feature_understanding")
    if version is None or version.stage != "feature_understanding":
        raise dynamic_error(
            ErrBadRequest,
            "选择的需求理解版本不存在或不属于当前需求"
            if version_id
            else "请先审核通过需求理解，再生成功能用例",
        )
    try:
        content = requirement_content(version.artifact_content)
    except ValueError as exc:
        raise dynamic_error(ErrBadRequest, "需求理解版本内容无效，请重新生成并审核") from exc
    if not content.strip():
        raise dynamic_error(ErrBadRequest, "需求理解版本内容为空，请重新生成并审核")
    return {
        "sourceContent": content,
        "requirementUnderstandingVersion": {
            "versionId": version.version_id,
            "versionNo": version.version_no,
            "taskId": version.task_id,
            "runId": version.run_id,
        },
    }
