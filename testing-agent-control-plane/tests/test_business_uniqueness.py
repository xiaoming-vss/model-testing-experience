"""Business keys remain reserved until their records are physically deleted."""


import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from testing_agent.models.project import Project


def test_only_hard_delete_releases_name():
    engine = create_engine("sqlite://")
    Project.__table__.create(engine)
    with Session(engine) as session:

        def create(key):
            return Project(project_id=key, user_id="user", name="same", description="")

        first = create("first")
        session.add(first)
        session.commit()
        session.add(create("duplicate"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.delete(first)
        session.commit()
        session.add(create("after-hard-delete"))
        session.commit()
    engine.dispose()
