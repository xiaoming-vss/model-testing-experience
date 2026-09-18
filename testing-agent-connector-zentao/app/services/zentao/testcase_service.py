import asyncio
from typing import Any

from app.clients.zentao.testcase_client import ZentaoTestCaseClient
from app.schemas.zentao.imports import (
    ImportListData,
    ImportListQuery,
    extract_total,
    first_value,
)
from app.schemas.zentao.testcase import (
    TestCaseBatchCreateData,
    TestCaseBatchCreateRequest,
    TestCaseCreateData,
    TestCaseImportData,
    extract_case_id,
)


class ZentaoTestCaseService:
    def __init__(
        self,
        testcase_client: ZentaoTestCaseClient,
    ) -> None:
        self._testcase_client = testcase_client

    async def create_testcases(
        self,
        payload: TestCaseBatchCreateRequest,
    ) -> TestCaseBatchCreateData:
        payloads = payload.to_zentao_payloads()
        existing_cases_by_title = await self._list_existing_execution_cases_by_title(
            payload.execution
        )
        items: list[TestCaseCreateData] = []
        for item in payloads:
            response_payload = await self._create_or_update_testcase(
                item,
                existing_cases_by_title,
            )
            items.append(TestCaseCreateData.from_upstream(response_payload))
        return TestCaseBatchCreateData(total=len(items), items=items)

    async def list_execution_cases(
        self,
        execution_id: int,
        query: ImportListQuery,
    ) -> ImportListData[TestCaseImportData]:
        testcase_list_payload = await self._testcase_client.list_execution_testcases(
            execution_id,
            params=query.to_zentao_params(),
        )
        testcase_items_with_ids = [
            (item, case_id)
            for item in testcase_list_payload.get("testcases", [])
            if isinstance(item, dict)
            for case_id in [extract_case_id(item)]
            if case_id is not None
        ]
        testcase_payloads = await asyncio.gather(
            *[self._testcase_client.get_testcase(case_id) for _, case_id in testcase_items_with_ids]
        )
        testcases = [
            TestCaseImportData.from_upstream(
                testcase_list_item,
                payload["testcase"],
                order_no=index,
            )
            for index, ((testcase_list_item, _), payload) in enumerate(
                zip(testcase_items_with_ids, testcase_payloads, strict=True),
                start=1,
            )
        ]
        return ImportListData(
            items=testcases,
            total=extract_total(testcase_list_payload, len(testcases)),
        )

    async def _create_or_update_testcase(
        self,
        payload: dict[str, Any],
        existing_cases_by_title: dict[str, int],
    ) -> dict[str, Any]:
        normalized_title = self._normalize_title(payload.get("title"))
        matched_case_id = existing_cases_by_title.get(normalized_title)
        if matched_case_id is None:
            created_payload = await self._testcase_client.create_testcase(payload)
            created_case_id = extract_case_id(created_payload)
            if created_case_id is not None:
                existing_cases_by_title[normalized_title] = created_case_id
            return created_payload

        updated_payload = await self._testcase_client.update_testcase(matched_case_id, payload)
        return {
            **updated_payload,
            "id": updated_payload.get("id", matched_case_id),
        }

    async def _list_existing_execution_cases_by_title(
        self,
        execution_id: int,
    ) -> dict[str, int]:
        if execution_id <= 0:
            return {}

        testcase_list_items: list[dict[str, Any]] = []
        page = 1
        page_size = 1000
        while True:
            testcase_list_payload = await self._testcase_client.list_execution_testcases(
                execution_id,
                params=ImportListQuery(page=page, page_size=page_size).to_zentao_params(),
            )
            page_items = [
                item
                for item in testcase_list_payload.get("testcases", [])
                if isinstance(item, dict)
            ]
            testcase_list_items.extend(page_items)
            total = extract_total(testcase_list_payload, len(testcase_list_items))
            if not page_items or len(testcase_list_items) >= total:
                break
            page += 1
        case_ids = [
            case_id
            for item in testcase_list_items
            for case_id in [extract_case_id(item)]
            if case_id is not None
        ]
        testcase_payloads = await asyncio.gather(
            *[self._testcase_client.get_testcase(case_id) for case_id in case_ids]
        )

        existing_cases_by_title: dict[str, int] = {}
        for payload in testcase_payloads:
            testcase = payload.get("testcase")
            if not isinstance(testcase, dict):
                continue
            case_id = extract_case_id(testcase)
            if case_id is None:
                continue
            normalized_title = self._normalize_title(first_value(testcase, "title", "name"))
            if not normalized_title:
                continue
            existing_cases_by_title.setdefault(normalized_title, case_id)
        return existing_cases_by_title

    @staticmethod
    def _normalize_title(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()
