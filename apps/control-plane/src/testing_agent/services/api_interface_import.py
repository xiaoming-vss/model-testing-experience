from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Any

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError

from testing_agent.core.config import get_settings
from testing_agent.core.errors import (
    AppError,
    ErrApiAppNotFound,
    ErrApiInterfaceIdentityAlreadyUse,
    ErrApiInterfaceImportBasePathForbidden,
    ErrApiInterfaceImportConflict,
    ErrApiInterfaceImportFileRequired,
    ErrApiInterfaceImportInvalid,
    ErrApiInterfaceImportSourceChanged,
    ErrApiInterfaceImportTooLarge,
    ErrBadRequest,
    dynamic_error,
)
from testing_agent.core.import_limits import ImportLimits
from testing_agent.core.sid import new_id
from testing_agent.domain.api_interface import normalize_rows, path_key
from testing_agent.domain.openapi_import import (
    ParsedEndpoint,
    ParsedOpenApiDocument,
    parse_openapi_document,
)
from testing_agent.domain.project_policy import allows_project_action
from testing_agent.models.api_app import ApiApp
from testing_agent.models.api_interface import ApiInterface
from testing_agent.models.project import Project
from testing_agent.repositories.api_app import ApiAppRepository
from testing_agent.repositories.api_interface import ApiInterfaceRepository
from testing_agent.schemas.api_interface_import import (
    ApiInterfaceImportApp,
    ApiInterfaceImportBasePathChange,
    ApiInterfaceImportCommitResponse,
    ApiInterfaceImportItem,
    ApiInterfaceImportPreviewResponse,
    ApiInterfaceImportResultItem,
    ApiInterfaceImportSource,
    ApiInterfaceImportSummary,
    ApiInterfaceImportWarning,
)
from testing_agent.services.import_budget import read_bounded
from testing_agent.services.project_access import (
    ProjectAction,
    project_role,
    require_project_id,
)

_CHANGE_ORDER = {"new": 0, "modified": 1, "unchanged": 2, "library_only": 3}
_DOC_FIELDS = (
    ("name", "name"),
    ("description", "description"),
    ("tags", "tags"),
    ("headers", "headers"),
    ("path_params", "pathParams"),
    ("query_params", "queryParams"),
    ("body_type", "bodyType"),
    ("body_schema", "bodySchema"),
    ("body_example", "bodyExample"),
    ("body_text", "bodyText"),
    ("response_status", "responseStatus"),
    ("response_description", "responseDescription"),
    ("response_schema", "responseSchema"),
    ("response_example", "responseExample"),
)


@dataclass(frozen=True, slots=True)
class _DiffItem:
    key: str
    change_type: str
    method: str
    path: str
    name: str
    endpoint: ParsedEndpoint | None
    existing: ApiInterface | None
    changed_fields: list[str]


def _canonical_rows(rows: list[dict[str, Any]] | None, location: str) -> list[tuple[Any, ...]]:
    normalized = normalize_rows(rows or [], location=location)  # type: ignore[arg-type]
    return sorted(
        (
            row["enabled"],
            row["name"].lower() if location == "header" else row["name"],
            row["type"],
            row["required"],
            row["example"],
            row["description"],
        )
        for row in normalized
    )


def _changed_fields(endpoint: ParsedEndpoint, interface: ApiInterface) -> list[str]:
    changed: list[str] = []
    row_locations = {
        "headers": "header",
        "path_params": "path",
        "query_params": "query",
    }
    for attr, api_name in _DOC_FIELDS:
        if attr in row_locations:
            expected = _canonical_rows(getattr(endpoint, attr), row_locations[attr])
            actual = _canonical_rows(getattr(interface, f"{attr}_json"), row_locations[attr])
            if expected != actual:
                changed.append(api_name)
        elif attr == "tags":
            if sorted(getattr(endpoint, attr) or []) != sorted(interface.tags_json or []):
                changed.append(api_name)
        else:
            expected = getattr(endpoint, attr)
            actual = (
                getattr(interface, f"{attr}_json")
                if attr in {"body_schema", "body_example", "response_schema", "response_example"}
                else getattr(interface, attr)
            )
            if expected != actual:
                changed.append(api_name)
    return changed


def _apply_endpoint(
    interface: ApiInterface,
    endpoint: ParsedEndpoint,
    parsed: ParsedOpenApiDocument,
    imported_at: datetime,
) -> None:
    interface.name = endpoint.name
    interface.description = endpoint.description
    interface.tags_json = endpoint.tags
    interface.headers_json = endpoint.headers
    interface.path_params_json = endpoint.path_params
    interface.query_params_json = endpoint.query_params
    interface.body_type = endpoint.body_type
    interface.body_schema_json = endpoint.body_schema
    interface.body_example_json = endpoint.body_example
    interface.body_text = endpoint.body_text
    interface.response_status = endpoint.response_status
    interface.response_description = endpoint.response_description
    interface.response_schema_json = endpoint.response_schema
    interface.response_example_json = endpoint.response_example
    interface.source_type = "openapi_file"
    interface.source_name = parsed.source_name
    interface.source_url = ""
    interface.source_version = parsed.source_version
    interface.source_imported_at = imported_at


class ApiInterfaceImportService:
    def __init__(
        self,
        interfaces: ApiInterfaceRepository,
        apps: ApiAppRepository,
        *,
        limits: ImportLimits | None = None,
    ) -> None:
        self.interfaces = interfaces
        self.apps = apps
        self.limits = limits or get_settings().asset_import

    async def preview(self, user_id: str, app_id: str, file: UploadFile | None) -> dict[str, Any]:
        app, project = await self._accessible_app(user_id, app_id, action="write")
        digest, parsed, _fallback = await self._parse_upload(file)
        current = await self.interfaces.list_all_by_app(app_id)
        items, summary = self._diff(parsed, current)
        role = await project_role(self.interfaces.session, user_id, project)
        can_apply = allows_project_action(role, "manage")
        base_path_change = None
        if parsed.base_path and parsed.base_path != app.base_path:
            base_path_change = ApiInterfaceImportBasePathChange(
                current=app.base_path,
                document=parsed.base_path,
                can_apply=can_apply,
            )
        response = ApiInterfaceImportPreviewResponse(
            source=ApiInterfaceImportSource(
                type="openapi_file",
                name=parsed.source_name,
                url="",
                version=parsed.source_version,
                digest=digest,
                base_path=parsed.base_path,
            ),
            app=ApiInterfaceImportApp(app_id=app.app_id, name=app.name, base_path=app.base_path),
            summary=ApiInterfaceImportSummary(**summary),
            base_path_change=base_path_change,
            warnings=[ApiInterfaceImportWarning(**warning) for warning in parsed.warnings],
            items=[
                ApiInterfaceImportItem(
                    key=item.key,
                    change_type=item.change_type,
                    method=item.method,
                    path=item.path,
                    name=item.name,
                    existing_interface_id=(item.existing.interface_id if item.existing else None),
                    existing_version=item.existing.version if item.existing else None,
                    changed_fields=item.changed_fields,
                )
                for item in items
            ],
        )
        return response.model_dump(by_alias=True, mode="json")

    async def commit(
        self,
        user_id: str,
        app_id: str,
        *,
        file: UploadFile | None,
        source_digest: str,
        selected_keys: str,
        expected_items: str,
        apply_base_path: bool,
        expected_app_version: int | None,
    ) -> dict[str, Any]:
        selected = self._selected_keys(selected_keys)
        expected = self._expected_items(expected_items)
        app = await self.apps.get(app_id)
        if app is None:
            raise ErrApiAppNotFound()
        await require_project_id(self.interfaces.session, user_id, app.project_id, action="write")
        # End the pre-check snapshot before parsing the upload. The write transaction below
        # must observe membership and interface rows committed while parsing.
        await self.interfaces.rollback()
        digest, parsed, _fallback = await self._parse_upload(file)
        if not source_digest or digest != source_digest:
            raise ErrApiInterfaceImportSourceChanged()

        app = await self.apps.get_for_update(app_id)
        if app is None:
            raise ErrApiAppNotFound()
        project = await require_project_id(
            self.interfaces.session, user_id, app.project_id, action="write"
        )
        role = await project_role(self.interfaces.session, user_id, project)
        base_path_changed = bool(parsed.base_path and parsed.base_path != app.base_path)
        if base_path_changed and not allows_project_action(role, "manage"):
            raise ErrApiInterfaceImportBasePathForbidden()
        if apply_base_path:
            if not allows_project_action(role, "manage"):
                raise ErrApiInterfaceImportBasePathForbidden()
            if not parsed.base_path:
                raise dynamic_error(ErrBadRequest, "文档没有可应用的 base path")
            if expected_app_version is None or expected_app_version != app.version:
                raise ErrApiInterfaceImportConflict()

        current = await self.interfaces.list_all_by_app(app_id)
        diff_items, summary = self._diff(parsed, current)
        by_key = {str(item.key): item for item in diff_items}
        selected_set = set(selected)
        unknown = selected_set - set(by_key)
        if unknown:
            raise dynamic_error(
                ErrApiInterfaceImportInvalid,
                f"导入项不存在：{', '.join(sorted(unknown))}",
            )
        if any(by_key[key].change_type == "library_only" for key in selected_set):
            raise dynamic_error(ErrApiInterfaceImportInvalid, "仅库中存在的接口不能被导入")

        now = datetime.now(UTC)
        created = 0
        updated = 0
        skipped = 0
        result_items: list[ApiInterfaceImportResultItem] = []
        for item in sorted(
            (by_key[key] for key in selected_set),
            key=lambda value: (value.method, value.path),
        ):
            endpoint = item.endpoint
            if endpoint is None or item.change_type in {"unchanged", "library_only"}:
                skipped += 1
                continue
            if item.existing is not None:
                expected_version = expected.get(item.key)
                if expected_version is None or expected_version != item.existing.version:
                    raise ErrApiInterfaceImportConflict()
                locked = await self.interfaces.get_by_identity_for_update(
                    app_id, endpoint.method, path_key(endpoint.path)
                )
                if locked is None or locked.version != expected_version:
                    raise ErrApiInterfaceImportConflict()
                _apply_endpoint(locked, endpoint, parsed, now)
                locked.version += 1
                updated += 1
                result_items.append(
                    ApiInterfaceImportResultItem(
                        key=item.key,
                        interface_id=locked.interface_id,
                        change_type="modified",
                    )
                )
            else:
                existing = await self.interfaces.get_by_identity_for_update(
                    app_id, endpoint.method, path_key(endpoint.path)
                )
                if existing is not None:
                    raise ErrApiInterfaceImportConflict()
                interface = ApiInterface(
                    interface_id=new_id(),
                    app_id=app_id,
                    method=endpoint.method,
                    path=endpoint.path,
                    path_key=path_key(endpoint.path),
                    enabled=True,
                    version=1,
                )
                _apply_endpoint(interface, endpoint, parsed, now)
                self.interfaces.add(interface)
                created += 1
                result_items.append(
                    ApiInterfaceImportResultItem(
                        key=item.key,
                        interface_id=interface.interface_id,
                        change_type="new",
                    )
                )

        if apply_base_path and parsed.base_path != app.base_path:
            app.base_path = parsed.base_path
            app.version += 1
        try:
            await self.interfaces.commit()
        except IntegrityError as exc:
            await self.interfaces.rollback()
            raise ErrApiInterfaceIdentityAlreadyUse() from exc
        response = ApiInterfaceImportCommitResponse(
            created=created,
            updated=updated,
            skipped=skipped,
            library_only=summary["library_only"],
            app_base_path=app.base_path,
            interfaces=result_items,
        )
        return response.model_dump(by_alias=True, mode="json")

    async def _accessible_app(
        self, user_id: str, app_id: str, *, action: ProjectAction
    ) -> tuple[ApiApp, Project]:
        app = await self.apps.get(app_id)
        if app is None:
            raise ErrApiAppNotFound()
        project = await require_project_id(
            self.interfaces.session, user_id, app.project_id, action=action
        )
        return app, project

    async def _parse_upload(
        self, file: UploadFile | None
    ) -> tuple[str, ParsedOpenApiDocument, str]:
        if file is None:
            raise ErrApiInterfaceImportFileRequired()
        if (file.size or 0) > self.limits.max_bytes:
            raise ErrApiInterfaceImportTooLarge()
        data = bytearray()
        while len(data) <= self.limits.max_bytes:
            chunk = await file.read(min(65536, self.limits.max_bytes + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > self.limits.max_bytes:
            raise ErrApiInterfaceImportTooLarge()
        raw = bytes(data)
        digest = hashlib.sha256(raw).hexdigest()
        try:
            # Bounded concurrency and off-loop parsing are shared with other asset importers.
            document = await read_bounded(raw, None, self.limits)
        except AppError as exc:
            if exc.http_code == 413:
                raise ErrApiInterfaceImportTooLarge() from exc
            if exc.http_code == 429:
                raise
            raise dynamic_error(ErrApiInterfaceImportInvalid, exc.message) from exc
        fallback_name = PurePath((file.filename or "").replace("\\", "/")).name
        try:
            parsed = await asyncio.to_thread(
                parse_openapi_document, document, fallback_name=fallback_name
            )
        except ValueError as exc:
            raise dynamic_error(ErrApiInterfaceImportInvalid, str(exc)) from exc
        if not parsed.endpoints:
            raise dynamic_error(ErrApiInterfaceImportInvalid, "文档中没有可导入的接口")
        return digest, parsed, fallback_name

    def _diff(
        self, parsed: ParsedOpenApiDocument, current: list[ApiInterface]
    ) -> tuple[list[_DiffItem], dict[str, int]]:
        current_by_key = {
            f"{interface.method} {interface.path}": interface for interface in current
        }
        document_keys: set[str] = set()
        items: list[_DiffItem] = []
        summary = {"new": 0, "modified": 0, "unchanged": 0, "library_only": 0}
        for endpoint in parsed.endpoints:
            key = f"{endpoint.method} {endpoint.path}"
            document_keys.add(key)
            existing = current_by_key.get(key)
            if existing is None:
                change_type = "new"
                changed_fields: list[str] = []
            else:
                changed_fields = _changed_fields(endpoint, existing)
                change_type = "modified" if changed_fields else "unchanged"
            summary[change_type] += 1
            items.append(
                _DiffItem(
                    key=key,
                    change_type=change_type,
                    method=endpoint.method,
                    path=endpoint.path,
                    name=endpoint.name,
                    endpoint=endpoint,
                    existing=existing,
                    changed_fields=changed_fields,
                )
            )
        for key, existing in current_by_key.items():
            if key in document_keys:
                continue
            summary["library_only"] += 1
            items.append(
                _DiffItem(
                    key=key,
                    change_type="library_only",
                    method=existing.method,
                    path=existing.path,
                    name=existing.name,
                    endpoint=None,
                    existing=existing,
                    changed_fields=[],
                )
            )
        items.sort(
            key=lambda item: (
                _CHANGE_ORDER[item.change_type],
                item.path,
                item.method,
            )
        )
        return items, summary

    def _selected_keys(self, value: str) -> list[str]:
        try:
            parsed = json.loads(value or "[]")
        except json.JSONDecodeError as exc:
            raise dynamic_error(ErrApiInterfaceImportInvalid, "selectedKeys 不是合法 JSON") from exc
        if not isinstance(parsed, list) or any(
            not isinstance(item, str) or not item.strip() for item in parsed
        ):
            raise dynamic_error(ErrApiInterfaceImportInvalid, "selectedKeys 必须是非空字符串数组")
        return list(dict.fromkeys(item.strip() for item in parsed))

    def _expected_items(self, value: str) -> dict[str, int]:
        try:
            parsed = json.loads(value or "{}")
        except json.JSONDecodeError as exc:
            raise dynamic_error(
                ErrApiInterfaceImportInvalid, "expectedItems 不是合法 JSON"
            ) from exc
        if not isinstance(parsed, dict):
            raise dynamic_error(ErrApiInterfaceImportInvalid, "expectedItems 必须是对象")
        result: dict[str, int] = {}
        for key, version in parsed.items():
            if (
                not isinstance(key, str)
                or not isinstance(version, int)
                or isinstance(version, bool)
            ):
                raise dynamic_error(ErrApiInterfaceImportInvalid, "expectedItems 的版本必须是整数")
            result[key] = version
        return result
