"""Freeze functional generation input from an approved material version."""

from typing import Any

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.repositories.generation_chain import GenerationChainRepository
from testing_agent.services.requirement_material_source import (
    approved_material,
    material_source,
    material_version_ref,
)

FUNCTIONAL_SOURCE_FORMAT = "requirement_understanding_json"
FUNCTIONAL_SOURCE_FORMAT_VERSION = "0.2"


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
        "sourceFormat": FUNCTIONAL_SOURCE_FORMAT,
        "sourceFormatVersion": FUNCTIONAL_SOURCE_FORMAT_VERSION,
        "requirementMaterialVersion": material_version_ref(version),
    }
