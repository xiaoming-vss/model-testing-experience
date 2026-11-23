"""Project selected API definitions into the exact generation input shape."""

from typing import Any

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.models.api_interface import ApiInterface
from testing_agent.models.software_repository import SoftwareRepository


def project_api_generation_snapshot(
    interface_ids: list[str], interfaces: list[ApiInterface], repositories: list[SoftwareRepository]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_id = {item.interface_id: item for item in interfaces}
    missing = [item for item in interface_ids if item not in by_id]
    if missing:
        raise dynamic_error(ErrBadRequest, f"选中的接口已删除：{', '.join(missing)}")
    repository_by_id = {item.software_repository_id: item for item in repositories}
    required = sorted({item.software_repository_id for item in interfaces})
    missing_repositories = [item for item in required if item not in repository_by_id]
    if missing_repositories:
        raise dynamic_error(
            ErrBadRequest, f"接口所属软件仓库已删除：{', '.join(missing_repositories)}"
        )

    def full_path(base_path: str, path: str) -> str:
        base = str(base_path or "").rstrip("/")
        normalized = path if path.startswith("/") else f"/{path}"
        return f"{base}{normalized}" if base else normalized

    return (
        [
            {
                "softwareRepositoryId": item.software_repository_id,
                "name": item.name,
                "basePath": item.base_path,
                "gitRepository": {
                    "instanceUrl": item.repository_instance_url,
                    "pathWithNamespace": item.repository_path,
                },
            }
            for item in repositories
        ],
        [
            {
                "interfaceId": item.interface_id,
                "softwareRepositoryId": item.software_repository_id,
                "softwareRepositoryName": repository_by_id[item.software_repository_id].name,
                "name": item.name,
                "method": item.method,
                "path": item.path,
                "fullPath": full_path(
                    repository_by_id[item.software_repository_id].base_path, item.path
                ),
                "description": item.description,
                "tags": item.tags_json or [],
                "headers": item.headers_json or [],
                "pathParams": item.path_params_json or [],
                "query": item.query_params_json or [],
                "bodyType": item.body_type,
                "bodySchema": item.body_schema_json,
                "bodyExample": item.body_example_json,
                "bodyText": item.body_text,
                "responseStatus": item.response_status,
                "responseDescription": item.response_description,
                "responseSchema": item.response_schema_json,
                "responseExample": item.response_example_json,
                "security": item.security_json,
                "securitySchemes": item.security_schemes_json,
            }
            for interface_id in interface_ids
            for item in [by_id[interface_id]]
        ],
    )
