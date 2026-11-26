from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from testing_agent.core.errors import (
    ErrBadRequest,
    ErrNotFound,
    ErrPerfCaseNameAlreadyUse,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.models.perf_case import PerfCase
from testing_agent.models.perf_suite import PerfSuite
from testing_agent.models.perf_suite_run import PerfSuiteRun
from testing_agent.repositories.perf_case import PerfCaseRepository
from testing_agent.repositories.perf_suite import PerfSuiteRepository
from testing_agent.repositories.perf_suite_run import PerfSuiteRunRepository
from testing_agent.schemas.perf_suite import (
    PerfSuiteCaseOrderUpdate,
    PerfSuiteCaseResponse,
    PerfSuiteCreate,
    PerfSuiteResponse,
    PerfSuiteSummaryResponse,
    PerfSuiteUpdate,
)
from testing_agent.services.perf_case_spec import parse_case_yaml
from testing_agent.services.project_access import ProjectAction, require_project_id
from testing_agent.services.resource_deletion import ResourceDeletion, SqlResourceDeletion
from testing_agent.services.stored_file import StoredFileService


class PerfSuiteService:
    def __init__(
        self,
        repository: PerfSuiteRepository,
        *,
        cases: PerfCaseRepository,
        runs: PerfSuiteRunRepository,
        files: StoredFileService | None = None,
        deletion: ResourceDeletion | None = None,
    ) -> None:
        self.repository = repository
        self.cases = cases
        self.runs = runs
        self.files = files
        self.deletion = deletion or SqlResourceDeletion()

    async def _accessible(self, user_id: str, suite_id: str, *, action: ProjectAction) -> PerfSuite:
        suite = await self.repository.get_suite(suite_id)
        if suite is None:
            raise ErrNotFound()
        await require_project_id(self.repository.session, user_id, suite.project_id, action=action)
        return suite

    def _case_payload(self, case: PerfCase) -> dict[str, Any]:
        return PerfSuiteCaseResponse(
            case_id=case.case_id,
            project_id=case.project_id,
            suite_id=case.suite_id or "",
            order_no=case.order_no,
            name=case.name,
            description=case.description,
            version=case.version,
            data_files=case.data_files_json or [],
            yaml=case.yaml,
            created_at=case.created_at,
            updated_at=case.updated_at,
            invalidated_at=case.invalidated_at,
        ).model_dump(by_alias=True, mode="json")

    def _summary(
        self,
        suite: PerfSuite,
        cases: list[PerfCase],
        last_run: PerfSuiteRun | None,
    ) -> dict[str, Any]:
        load_models: list[str] = []
        step_count = 0
        data_file_count = 0
        for case in cases:
            try:
                parsed = parse_case_yaml(case.yaml)
            except Exception:
                continue
            case_spec = parsed.get("case") or {}
            steps = case_spec.get("steps") or []
            data = case_spec.get("data") or []
            load = case_spec.get("load") or {}
            step_count += len(steps)
            data_file_count += len(data)
            model = str(load.get("model") or "")
            if model and model not in load_models:
                load_models.append(model)
        response = PerfSuiteSummaryResponse(
            suite_id=suite.suite_id,
            project_id=suite.project_id,
            name=suite.name,
            description=suite.description,
            case_count=len(cases),
            step_count=step_count,
            data_file_count=data_file_count,
            load_models=load_models,
            last_run_status=last_run.status if last_run else "",
            last_run_outcome=last_run.outcome or "" if last_run else "",
            created_at=suite.created_at,
            updated_at=suite.updated_at,
        )
        return response.model_dump(by_alias=True, mode="json")

    async def _detail(self, suite: PerfSuite, *, include_cases: bool) -> dict[str, Any]:
        cases = await self.cases.list_by_suite(suite.suite_id)
        last_run = await self.runs.latest_by_suite(suite.suite_id)
        data = self._summary(suite, cases, last_run)
        if include_cases:
            data["cases"] = [self._case_payload(case) for case in cases]
            data["createdBy"] = suite.created_by
            return PerfSuiteResponse.model_validate(data).model_dump(by_alias=True, mode="json")
        return data

    async def create(self, user_id: str, project_id: str, body: PerfSuiteCreate) -> dict[str, Any]:
        await require_project_id(self.repository.session, user_id, project_id, action="write")
        name = body.name.strip()
        if await self.repository.get_by_project_and_name(project_id, name) is not None:
            raise dynamic_error(ErrPerfCaseNameAlreadyUse, "该性能测试集名称已存在")
        suite = PerfSuite(
            suite_id=new_id(),
            project_id=project_id,
            name=name,
            description=body.description.strip(),
            created_by=user_id,
        )
        self.repository.add(suite)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise dynamic_error(ErrPerfCaseNameAlreadyUse, "该性能测试集名称已存在") from exc
        await self.repository.refresh(suite)
        return await self._detail(suite, include_cases=True)

    async def list(self, user_id: str, project_id: str) -> dict[str, Any]:
        await require_project_id(self.repository.session, user_id, project_id, action="read")
        suites = await self.repository.list_by_project(project_id)
        items = []
        for suite in suites:
            cases = await self.cases.list_by_suite(suite.suite_id)
            last_run = await self.runs.latest_by_suite(suite.suite_id)
            items.append(self._summary(suite, cases, last_run))
        return {"total": len(items), "items": items}

    async def get(self, user_id: str, suite_id: str) -> dict[str, Any]:
        suite = await self._accessible(user_id, suite_id, action="read")
        return await self._detail(suite, include_cases=True)

    async def update(self, user_id: str, suite_id: str, body: PerfSuiteUpdate) -> dict[str, Any]:
        suite = await self.repository.get_suite(suite_id, for_update=True)
        if suite is None:
            raise ErrNotFound()
        await require_project_id(self.repository.session, user_id, suite.project_id, action="write")
        fields = body.model_fields_set
        changed = False
        if "name" in fields:
            if body.name is None:
                raise ErrBadRequest()
            name = body.name.strip()
            if name != suite.name and (
                await self.repository.get_by_project_and_name(suite.project_id, name) is not None
            ):
                raise dynamic_error(ErrPerfCaseNameAlreadyUse, "该性能测试集名称已存在")
            suite.name = name
            changed = True
        if "description" in fields and body.description is not None:
            suite.description = body.description.strip()
            changed = True
        if changed:
            suite.updated_at = datetime.now(UTC)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise dynamic_error(ErrPerfCaseNameAlreadyUse, "该性能测试集名称已存在") from exc
        await self.repository.refresh(suite)
        return await self._detail(suite, include_cases=True)

    async def reorder(
        self, user_id: str, suite_id: str, body: PerfSuiteCaseOrderUpdate
    ) -> dict[str, Any]:
        suite = await self._accessible(user_id, suite_id, action="write")
        cases = await self.cases.list_by_suite(suite.suite_id)
        by_id = {case.case_id: case for case in cases}
        if len(body.case_ids) != len(set(body.case_ids)) or set(body.case_ids) != set(by_id):
            raise ErrBadRequest()
        for index, case_id in enumerate(body.case_ids, start=1):
            by_id[case_id].order_no = index
        suite.updated_at = datetime.now(UTC)
        await self.repository.commit()
        return await self._detail(suite, include_cases=True)

    async def delete(self, user_id: str, suite_id: str) -> dict[str, Any]:
        suite = await self._accessible(user_id, suite_id, action="write")
        cases = await self.cases.list_by_suite(suite.suite_id)
        if self.files is not None and cases:
            now = datetime.now(UTC).replace(tzinfo=None)
            for case in cases:
                rows = await self.files.list_by_resource(case.project_id, "perf_case", case.case_id)
                for row in rows:
                    row.status = "deleting"
                    row.expires_at = now
        await self.deletion.delete(self.repository.session, suite)
        await self.repository.commit()
        return {}
