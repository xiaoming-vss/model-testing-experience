from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from testing_agent.core.errors import (
    ErrFunctionTestCaseImportInvalid,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.domain.function_case_content import CaseContent
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.repositories.function_test_case import FunctionTestCaseRepository
from testing_agent.services.function_case_access import FunctionCaseAccess
from testing_agent.services.import_payload import (
    import_items,
    read_import_payload,
)


class FunctionCaseImporter:
    def __init__(self, repository: FunctionTestCaseRepository) -> None:
        self.repository = repository
        self.access = FunctionCaseAccess(repository)

    async def import_cases(self, user_id: str, suite_id: str, payload: Any, file: Any) -> dict:
        await self.access.get_accessible_suite(user_id, suite_id, action="write")
        # Authorization reads must not hold a connection while parsing an upload.
        await self.repository.session.rollback()
        parsed = await read_import_payload(payload, file)
        rows = []
        for index, item in enumerate(import_items(parsed, "cases", "functionCases", "testcases")):
            if not isinstance(item, dict):
                raise dynamic_error(
                    ErrFunctionTestCaseImportInvalid, f"第 {index + 1} 条用例必须是对象"
                )
            try:
                order_no = int(item.get("orderNo", item.get("order_no", index)) or 0)
            except (ValueError, TypeError, OverflowError):
                raise dynamic_error(
                    ErrFunctionTestCaseImportInvalid, f"第 {index + 1} 条用例顺序必须是整数"
                ) from None
            content = item.get("content")
            if content is not None:
                try:
                    content = CaseContent.model_validate(content).model_dump()
                except ValidationError as exc:
                    raise dynamic_error(
                        ErrFunctionTestCaseImportInvalid,
                        f"第 {index + 1} 条用例正文格式不正确",
                    ) from exc
            rows.append(
                FunctionTestCase(
                    case_id=new_id(),
                    suite_id=suite_id,
                    content=content,
                    module=str(item.get("module") or ""),
                    title=str(
                        item.get("title") or item.get("name") or f"Function Case {index + 1}"
                    ),
                    preconditions=str(item.get("preconditions") or item.get("precondition") or ""),
                    steps=str(item.get("steps") or ""),
                    expected_results=str(
                        item.get("expectedResults") or item.get("expected_results") or ""
                    ),
                    priority=str(item.get("priority") or ""),
                    case_type=str(item.get("caseType") or item.get("case_type") or ""),
                    order_no=order_no,
                )
            )
        await self.access.get_accessible_suite(user_id, suite_id, action="write")
        for row in rows:
            self.repository.add(row)
        await self.repository.commit()
        return {"imported": len(rows)}
