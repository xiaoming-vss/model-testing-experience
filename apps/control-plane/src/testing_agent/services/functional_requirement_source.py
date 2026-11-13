"""Freeze functional generation input from an approved material version."""

from typing import Any

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.repositories.generation_chain import GenerationChainRepository
from testing_agent.services.requirement_material_source import (
    approved_material,
    material_source,
    material_version_ref,
)


async def functional_requirement_source(
    repository: GenerationChainRepository, requirement_id: str, version_id: str = ""
) -> dict[str, Any]:
    version = await approved_material(repository, requirement_id, version_id)
    if version is None:
        raise dynamic_error(ErrBadRequest, "请先审核通过材料整理，再生成功能用例")
    content = material_source(version)
    if not content.strip():
        raise dynamic_error(ErrBadRequest, "材料整理版本内容为空，请重新生成并审核")
    return {
        "sourceContent": content,
        "requirementMaterialVersion": material_version_ref(version),
        # 功能用例消费的是材料整理结果，不是原始材料文件；显式声明类型，
        # 避免 Worker 回退使用 sourceType="requirement" 作为文档类型。
        "documentType": "text",
    }
