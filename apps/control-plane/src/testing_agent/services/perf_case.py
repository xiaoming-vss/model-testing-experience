from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
    ErrPerfCaseNameAlreadyUse,
    ErrPerfCaseNotFound,
    ErrPerfDataFileMissing,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.models.perf_case import PerfCase
from testing_agent.repositories.perf_case import PerfCaseRepository
from testing_agent.repositories.perf_suite import PerfSuiteRepository
from testing_agent.schemas.perf_case import PerfCaseCreate, PerfCaseResponse, PerfCaseUpdate
from testing_agent.services.case_lifecycle import (
    batch_set_invalidated,
)
from testing_agent.services.perf_case_spec import case_data_sources, parse_case_yaml
from testing_agent.services.project_access import ProjectAction, require_project_id
from testing_agent.services.resource_deletion import ResourceDeletion, SqlResourceDeletion
from testing_agent.services.stored_file import StoredFileService

MAX_DATA_FILES = 20
MAX_DATA_FILES_BYTES = 100 * 1024 * 1024
_DATA_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(csv|json)$")


class PerfCaseService:
    def __init__(
        self,
        repository: PerfCaseRepository,
        *,
        files: StoredFileService,
        deletion: ResourceDeletion | None = None,
        suites: PerfSuiteRepository | None = None,
    ) -> None:
        self.repository = repository
        self.files = files
        self.deletion = deletion or SqlResourceDeletion()
        self.suites = suites or PerfSuiteRepository(repository.session)

    async def _require_project(self, user_id: str, project_id: str, action: ProjectAction) -> None:
        await require_project_id(self.repository.session, user_id, project_id, action=action)

    async def _accessible(self, user_id: str, case_id: str, *, action: ProjectAction) -> PerfCase:
        case = await self.repository.get_case(case_id)
        if case is None:
            raise ErrPerfCaseNotFound()
        await self._require_project(user_id, case.project_id, action)
        return case

    async def _attach_files_async(
        self,
        user_id: str,
        project_id: str,
        case_id: str,
        file_ids: list[str],
    ) -> list[Any]:
        rows = []
        seen: set[str] = set()
        for file_id in file_ids:
            if file_id in seen:
                raise ErrBadRequest()
            seen.add(file_id)
            row = await self.files.attach(
                user_id,
                file_id,
                project_id,
                "perf_case",
                case_id,
                purpose="perf_case_data",
            )
            rows.append(row)
        if len(rows) > MAX_DATA_FILES:
            raise AppError(400, "单个性能用例最多关联 20 个数据文件", 400)
        total = 0
        names: set[str] = set()
        for row in rows:
            if not _DATA_FILENAME_RE.fullmatch(row.filename):
                raise AppError(400, "数据文件名只能包含字母、数字、点、下划线和连字符", 400)
            if row.filename in names:
                raise AppError(400, f"数据文件名重复: {row.filename}", 400)
            names.add(row.filename)
            total += row.size
        if total > MAX_DATA_FILES_BYTES:
            raise AppError(400, "数据文件总大小超过 100MB 限制", 400)
        return rows

    def _metadata(self, rows: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "fileId": row.file_id,
                "filename": row.filename,
                "size": row.size,
                "sha256": row.sha256,
            }
            for row in rows
        ]

    def _validate_sources(self, parsed: dict[str, Any], metadata: list[dict[str, Any]]) -> None:
        filenames = {item["filename"] for item in metadata}
        missing = sorted(case_data_sources(parsed) - filenames)
        if missing:
            raise dynamic_error(
                ErrPerfDataFileMissing,
                f"性能用例引用了未关联的数据文件: {', '.join(missing)}",
            )

    async def _require_suite(self, project_id: str, suite_id: str):
        suite = await self.suites.get_suite(suite_id)
        if suite is None or suite.project_id != project_id:
            raise ErrBadRequest()
        return suite

    def _detail(self, case: PerfCase) -> dict[str, Any]:
        response = PerfCaseResponse(
            case_id=case.case_id,
            project_id=case.project_id,
            suite_id=case.suite_id or "",
            order_no=case.order_no,
            name=case.name,
            description=case.description,
            yaml=case.yaml,
            version=case.version,
            data_files=case.data_files_json or [],
            created_by=case.created_by,
            created_at=case.created_at,
            updated_at=case.updated_at,
            invalidated_at=case.invalidated_at,
        )
        return response.model_dump(by_alias=True, mode="json")

    async def create(self, user_id: str, project_id: str, body: PerfCaseCreate) -> dict[str, Any]:
        await self._require_project(user_id, project_id, "write")
        name = body.name.strip()
        if await self.repository.get_by_project_and_name(project_id, name) is not None:
            raise ErrPerfCaseNameAlreadyUse()
        suite_id = body.suite_id or None
        order_no = body.order_no
        if suite_id is not None:
            await self._require_suite(project_id, suite_id)
            if order_no is None:
                order_no = await self.repository.next_order_no(suite_id)
        parsed = parse_case_yaml(body.yaml)
        case_id = new_id()
        rows = await self._attach_files_async(user_id, project_id, case_id, body.data_file_ids)
        metadata = self._metadata(rows)
        self._validate_sources(parsed, metadata)
        case = PerfCase(
            case_id=case_id,
            project_id=project_id,
            suite_id=suite_id,
            order_no=order_no or 0,
            name=name,
            description=body.description.strip(),
            yaml=body.yaml,
            version=1,
            data_files_json=metadata,
            created_by=user_id,
        )
        self.repository.add(case)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ErrPerfCaseNameAlreadyUse() from exc
        await self.repository.refresh(case)
        return self._detail(case)

    async def batch_set_invalidated(
        self, user_id: str, project_id: str, case_ids: Sequence[str], invalidated: bool
    ) -> dict:
        return await batch_set_invalidated(
            self.repository,
            self.repository.session,
            user_id,
            project_id,
            case_ids,
            invalidated,
        )

    async def update(self, user_id: str, case_id: str, body: PerfCaseUpdate) -> dict[str, Any]:
        case = await self.repository.get_case(case_id, for_update=True)
        if case is None:
            raise ErrPerfCaseNotFound()
        await self._require_project(user_id, case.project_id, "write")
        fields = body.model_fields_set
        changed = False
        if "name" in fields:
            if body.name is None:
                raise ErrBadRequest()
            name = body.name.strip()
            if name != case.name and (
                await self.repository.get_by_project_and_name(case.project_id, name) is not None
            ):
                raise ErrPerfCaseNameAlreadyUse()
            case.name = name
            changed = True
        if "description" in fields and body.description is not None:
            case.description = body.description.strip()
            changed = True
        metadata = case.data_files_json or []
        if "data_file_ids" in fields:
            if body.data_file_ids is None:
                raise ErrBadRequest()
            rows = await self._attach_files_async(
                user_id, case.project_id, case.case_id, body.data_file_ids
            )
            metadata = self._metadata(rows)
            case.data_files_json = metadata
            changed = True
        yaml_text = case.yaml
        if "yaml" in fields:
            if body.yaml is None:
                raise ErrBadRequest()
            yaml_text = body.yaml
            changed = True
        parsed = parse_case_yaml(yaml_text)
        self._validate_sources(parsed, metadata)
        case.yaml = yaml_text
        if "order_no" in fields and body.order_no is not None:
            case.order_no = body.order_no
            changed = True
        if changed:
            case.version += 1
            case.updated_at = datetime.now(UTC)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ErrPerfCaseNameAlreadyUse() from exc
        await self.repository.refresh(case)
        return self._detail(case)

    async def delete(self, user_id: str, case_id: str) -> dict[str, Any]:
        case = await self._accessible(user_id, case_id, action="write")
        data_files = await self.files.list_by_resource(case.project_id, "perf_case", case.case_id)
        now = datetime.now(UTC).replace(tzinfo=None)
        for row in data_files:
            row.status = "deleting"
            row.expires_at = now
        await self.deletion.delete(self.repository.session, case)
        await self.repository.commit()
        return {}
