"""Deliver provider credentials only from a caller's own authorized connection."""

from testing_agent.core.enums import ConnectionStatus
from testing_agent.core.errors import ErrIntegrationConnectionAuthFailed, ErrNotFound
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.services.integration_credentials import IntegrationCredentialCipher


class PersonalCredentialAccess:
    def __init__(self, cipher: IntegrationCredentialCipher | None) -> None:
        self.cipher = cipher

    def _require_owner(
        self, connection: IntegrationConnection, user_id: str, provider: str, project_id: str
    ) -> None:
        if (
            not user_id
            or connection.user_id != user_id
            or connection.provider != provider
            or connection.project_id not in ("", project_id)
        ):
            raise ErrNotFound()
        if connection.status != ConnectionStatus.ACTIVE.value:
            raise ErrIntegrationConnectionAuthFailed()

    def _decrypt(self, ciphertext: object) -> str:
        if not isinstance(ciphertext, str) or not ciphertext:
            raise ErrIntegrationConnectionAuthFailed()
        if self.cipher is None:
            raise RuntimeError("未配置集成凭据加密器")
        return self.cipher.decrypt(ciphertext)

    def gitlab_token(
        self, connection: IntegrationConnection, *, user_id: str, project_id: str
    ) -> str:
        """Deliver the selected owner's PAT after the resource query authorizes it.

        The existing standalone GitLab query permits omitted project scope;
        preserve that behavior for the owner's selected connection. A supplied
        project must still match, and no role bypass grants another owner's PAT.
        """
        self._require_owner(connection, user_id, "gitlab", project_id or connection.project_id)
        return self._decrypt(connection.access_token)

    def mcp_token(
        self,
        connection: IntegrationConnection,
        *,
        user_id: str,
        project_id: str,
    ) -> str:
        """Read a token from a current, caller-owned connection.

        The caller obtains the row through an authorized query, refreshing or
        locking it when its operation requires current state. This method checks
        ownership and scope again before decrypting; it neither queries nor
        commits, so it can also be used inside the caller's locked transaction.
        Project roles, shared-service selection and instance checks remain with
        their business operation. No administrator bypass grants another token.
        """
        self._require_owner(connection, user_id, "mcp", project_id)
        return self._decrypt((connection.secret_json or {}).get("token"))
