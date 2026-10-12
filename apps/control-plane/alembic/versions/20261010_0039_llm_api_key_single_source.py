"""Keep llm API keys only in secret_json; clear the legacy access_token copy.

Connections historically stored the encrypted API key twice (secret_json.apiKey
and access_token). Reads prefer secret_json and keep access_token as a fallback
for pre-migration rows, so blanking the duplicate copy is safe.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261010_0039"
down_revision = "20261010_0038"
branch_labels = None
depends_on = None

# As the current head, this revision owns the downgrade evidence gate: the same
# checks as 20261007_0032 must run before ANY structural change in the chain,
# otherwise a refused downgrade would leave earlier revisions already applied.
GUARDS = (
    (
        "SELECT COUNT(*) FROM integration_restore_reviews",
        "恢复核对证据必须保留，禁止删除执行证据",
    ),
    (
        "SELECT COUNT(*) FROM integration_runtime WHERE blocked=1",
        "恢复环境尚未核对，禁止删除隔离标记",
    ),
    (
        "SELECT COUNT(*) FROM integration_jobs WHERE recovery_required=1 OR status IN "
        "('queued','claimed','running','unknown','quarantined')",
        "集成任务尚未完成核对，禁止删除执行证据",
    ),
    (
        "SELECT COUNT(*) FROM integration_job_steps WHERE status IN ('write_intent','unknown')",
        "集成任务尚未完成核对，禁止删除执行证据",
    ),
)


def _require_safe_downgrade():
    connection = op.get_bind()
    if connection.dialect.name != "mysql":
        return
    for statement, message in GUARDS:
        if connection.scalar(sa.text(statement)):
            raise RuntimeError(message)


def upgrade():
    if op.get_bind().dialect.name == "mysql":
        op.execute(
            "UPDATE integration_connections SET access_token = ''"
            " WHERE auth_type = 'api_key' AND access_token != ''"
        )


def downgrade():
    # The cleared values were duplicates of secret_json.apiKey ciphertext
    # re-encrypted under the same key; they cannot be reconstructed verbatim
    # and do not need to be: readers fall back to secret_json.
    _require_safe_downgrade()
