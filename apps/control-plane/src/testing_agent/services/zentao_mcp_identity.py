"""Detect target changes so an owner can reset the project's remote associations."""

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import load_only

from testing_agent.core.errors import AppError
from testing_agent.models.bug import Bug
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.requirement import Requirement
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.shared_service import ServiceAuthorization, SharedService
from testing_agent.models.sprint import Sprint
from testing_agent.services.service_instance import instance_key
from testing_agent.services.zentao_mcp_selection import binding_service_id


def project_binding_scope(project_id):
    sprint_ids = select(Sprint.sprint_id).where(Sprint.project_id == project_id)
    requirement_ids = select(Requirement.requirement_id).where(
        Requirement.sprint_id.in_(sprint_ids)
    )
    return and_(
        ResourceBinding.provider == "zentao",
        or_(
            and_(
                ResourceBinding.local_resource_type == "project",
                ResourceBinding.local_resource_id == project_id,
            ),
            and_(
                ResourceBinding.local_resource_type == "sprint",
                ResourceBinding.local_resource_id.in_(sprint_ids),
            ),
            and_(
                ResourceBinding.local_resource_type == "requirement",
                ResourceBinding.local_resource_id.in_(requirement_ids),
            ),
        ),
    )


async def service_associations(session, resource):
    services = list(
        await session.scalars(
            select(SharedService).where(
                SharedService.project_id == resource.project_id,
                SharedService.provider == "mcp",
                SharedService.template_id == "zentao",
            )
        )
    )
    ids = {row.service_id for row in services}
    authorizations = dict(
        (
            await session.execute(
                select(ServiceAuthorization.connection_id, ServiceAuthorization.service_id).where(
                    ServiceAuthorization.service_id.in_(ids)
                )
            )
        ).all()
    )

    def owns(identifier, instance):
        if identifier in ids:
            return identifier == resource.service_id
        if len(services) == 1:
            return True  # Sole legacy or recreated catalog, before explicit selection existed.
        candidates = [
            row.service_id
            for row in services
            if row.zentao_instance_url
            and instance_key(row.zentao_instance_url) == instance_key(instance)
        ]
        return candidates == [resource.service_id]

    bindings = list(
        await session.scalars(
            select(ResourceBinding)
            .options(
                load_only(
                    ResourceBinding.binding_id,
                    ResourceBinding.connection_id,
                    ResourceBinding.instance_url,
                    ResourceBinding.extra_json,
                    ResourceBinding.local_resource_type,
                    ResourceBinding.local_resource_id,
                )
            )
            .where(project_binding_scope(resource.project_id))
        )
    )
    bindings = [
        row
        for row in bindings
        if owns(
            binding_service_id(row) or authorizations.get(row.connection_id, ""), row.instance_url
        )
    ]
    pushes = list(
        await session.scalars(
            select(BugZentaoPush)
            .options(
                load_only(
                    BugZentaoPush.bug_id, BugZentaoPush.service_id, BugZentaoPush.instance_url
                )
            )
            .join(Bug, Bug.bug_id == BugZentaoPush.bug_id)
            .where(Bug.project_id == resource.project_id)
        )
    )
    push_services = {row.bug_id: row.service_id for row in pushes}
    owned_pushes = [row for row in pushes if owns(row.service_id, row.instance_url)]
    attachments = list(
        await session.scalars(
            select(BugZentaoAttachment)
            .options(
                load_only(
                    BugZentaoAttachment.id,
                    BugZentaoAttachment.bug_id,
                    BugZentaoAttachment.file_id,
                    BugZentaoAttachment.instance_url,
                )
            )
            .join(Bug, Bug.bug_id == BugZentaoAttachment.bug_id)
            .where(Bug.project_id == resource.project_id)
        )
    )
    attachments = [
        row for row in attachments if owns(push_services.get(row.bug_id, ""), row.instance_url)
    ]
    return bindings, owned_pushes, attachments


async def historical_instances(session, project_id, resource=None):
    if resource is not None:
        bindings, pushes, attachments = await service_associations(session, resource)
        targets = {row.instance_url for row in [*bindings, *pushes, *attachments]}
    else:
        targets = set(
            await session.scalars(
                select(ResourceBinding.instance_url).where(project_binding_scope(project_id))
            )
        )
        for model in (BugZentaoPush, BugZentaoAttachment):
            targets.update(
                await session.scalars(
                    select(model.instance_url)
                    .join(Bug, Bug.bug_id == model.bug_id)
                    .where(Bug.project_id == project_id)
                )
            )
    return {instance_key(target) for target in targets if target}


async def needs_instance_reset(session, resource, info):
    current = instance_key(info["instanceUrl"])
    history = await historical_instances(session, resource.project_id, resource)
    changed = bool(
        resource.zentao_instance_url and instance_key(resource.zentao_instance_url) != current
    )
    return changed or any(target != current for target in history)


async def validate_identity(session, resource, info):
    if await needs_instance_reset(session, resource, info):
        raise AppError(
            409, "禅道目标已变更或存在旧绑定，请项目所有者在编辑服务中勾选确认后保存", 409
        )
