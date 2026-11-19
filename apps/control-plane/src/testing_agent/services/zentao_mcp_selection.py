"""Resolve project MCP choices without selecting another member's credentials."""

from testing_agent.core.errors import AppError
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.repositories.shared_service_catalog import SharedServiceCatalogRepository
from testing_agent.services.service_instance import instance_key


def binding_service_id(binding):
    return str((getattr(binding, "extra_json", None) or {}).get("mcpServiceId") or "")


async def project_binding(session, project_id):
    return await ResourceBindingRepository(session).active_project_binding(project_id)


async def inherited_mcp_service_id(session, project_id, requested=""):
    binding = await project_binding(session, project_id)
    inherited = binding_service_id(binding)
    if requested and requested != inherited:
        raise AppError(400, "下级绑定须使用项目绑定所选的禅道 MCP", 400)
    return inherited or requested


async def select_mcp_service(session, project_id, service_id="", expected_instance=""):
    services = await SharedServiceCatalogRepository(session).zentao_mcp_services(project_id)
    if not service_id:
        binding = await project_binding(session, project_id)
        service_id = binding_service_id(binding)
        expected_instance = expected_instance or (binding.instance_url if binding else "")
    if service_id:
        chosen = next((row for row in services if row.service_id == service_id), None)
        if chosen is None:
            raise AppError(400, "所选禅道 MCP 不存在或不属于当前项目，请重新选择", 400)
        return chosen
    if len(services) == 1:
        return services[0]
    if expected_instance:
        matches = [
            row
            for row in services
            if row.zentao_instance_url
            and instance_key(row.zentao_instance_url) == instance_key(expected_instance)
        ]
        if len(matches) == 1:
            return matches[0]
    if not services:
        raise AppError(400, "请先在基础服务配置禅道 MCP", 400)
    raise AppError(400, "当前项目有多个禅道 MCP，请先在项目绑定中选择 MCP", 400)
