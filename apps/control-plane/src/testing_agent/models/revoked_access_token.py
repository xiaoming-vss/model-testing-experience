from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base


class RevokedAccessToken(Base):
    __tablename__ = "revoked_access_tokens"
    __table_args__ = {"comment": "已撤销登录令牌的摘要及到期时间"}

    token_hash: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="已撤销 JWT 令牌的 SHA-256 摘要"
    )
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        comment="用户业务标识",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="有效期或清理期限截止时间（UTC）",
    )
