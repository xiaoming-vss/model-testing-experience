from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FunctionCaseQuery:
    """用例库检索条件：项目范围内的用例按迭代 / 需求 / 测试集与用例属性筛选后的一个分页窗口。"""

    project_id: str
    sprint_id: str = ""
    requirement_id: str = ""
    suite_id: str = ""
    module: str = ""
    priority: str = ""
    case_type: str = ""
    keyword: str = ""
    limit: int = 20
    offset: int = 0

    @classmethod
    def for_page(
        cls,
        project_id: str,
        *,
        page: int,
        page_size: int,
        sprint_id: str = "",
        requirement_id: str = "",
        suite_id: str = "",
        module: str = "",
        priority: str = "",
        case_type: str = "",
        keyword: str = "",
    ) -> FunctionCaseQuery:
        return cls(
            project_id=project_id,
            sprint_id=sprint_id.strip(),
            requirement_id=requirement_id.strip(),
            suite_id=suite_id.strip(),
            module=module.strip(),
            priority=priority.strip(),
            case_type=case_type.strip(),
            keyword=keyword.strip(),
            limit=page_size,
            offset=(page - 1) * page_size,
        )
