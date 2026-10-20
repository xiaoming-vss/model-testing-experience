"""Project roles and immutable action policy, independent of storage and request transport."""

from functools import lru_cache
from typing import Literal

import casbin  # type: ignore[import-untyped]

ProjectAction = Literal[
    "read", "write", "execute", "review", "manage", "project_read", "bug_read", "bug_handle"
]
ACTIONS: tuple[ProjectAction, ...] = (
    "read",
    "write",
    "execute",
    "review",
    "manage",
    "project_read",
    "bug_read",
    "bug_handle",
)


@lru_cache(maxsize=1)
def _policy() -> casbin.Enforcer:
    model = casbin.Model()
    model.load_model_from_text("""
[request_definition]
r = role, action
[policy_definition]
p = role, action
[role_definition]
g = _, _
[policy_effect]
e = some(where (p.eft == allow))
[matchers]
m = g(r.role, p.role) && r.action == p.action
""")
    enforcer = casbin.Enforcer(model)
    enforcer.add_policy("viewer", "read")
    for role in ("viewer", "developer"):
        enforcer.add_policy(role, "project_read")
        enforcer.add_policy(role, "bug_read")
    enforcer.add_policy("developer", "bug_handle")
    enforcer.add_policy("member", "bug_handle")
    for action in ("write", "execute", "review"):
        enforcer.add_policy("member", action)
    enforcer.add_policy("owner", "manage")
    enforcer.add_grouping_policy("member", "viewer")
    enforcer.add_grouping_policy("owner", "member")
    return enforcer


def allowed_actions(role: str) -> list[str]:
    return [action for action in ACTIONS if _policy().enforce(role, action)]


def effective_project_role(
    *, is_owner: bool, member_role: str | None, is_super_admin: bool = False
) -> str:
    """Callers supply trusted facts; execution paths may intentionally omit admin privilege."""
    return "owner" if is_owner or is_super_admin else member_role or ""


def allows_project_action(role: str, action: ProjectAction) -> bool:
    return bool(_policy().enforce(role, action))
