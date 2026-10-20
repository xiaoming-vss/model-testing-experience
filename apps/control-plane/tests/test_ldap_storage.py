from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from testing_agent.models.login_rate_limit import LoginRateLimit
from testing_agent.models.user import User


def test_external_identity_unique_but_multiple_local_nulls_allowed():
    engine = create_engine("sqlite://")
    User.__table__.create(engine)
    with Session(engine) as session:
        for name in ("a", "b"):
            session.add(User(user_id=name, nickname=name, password="", auth_source="local"))
        session.commit()
        session.add(
            User(
                user_id="c",
                nickname="c",
                password="",
                auth_source="ldap",
                external_id="550e8400-e29b-41d4-a716-446655440000",
            )
        )
        session.commit()
        session.add(
            User(
                user_id="d",
                nickname="d",
                password="",
                auth_source="ldap",
                external_id="550e8400-e29b-41d4-a716-446655440000",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert len(session.scalars(select(User)).all()) == 3
    engine.dispose()


def test_same_username_ip_has_independent_authentication_limits():
    engine = create_engine("sqlite://")
    LoginRateLimit.__table__.create(engine)
    with Session(engine) as session:
        for method, count in (("ldap", 5), ("local", 0)):
            session.add(
                LoginRateLimit(
                    auth_method=method,
                    username="root",
                    client_ip="127.0.0.1",
                    attempt_count=count,
                    window_started_at=datetime.now(UTC),
                )
            )
        session.commit()
        local = session.scalar(select(LoginRateLimit).where(LoginRateLimit.auth_method == "local"))
        assert local.attempt_count == 0
    engine.dispose()
