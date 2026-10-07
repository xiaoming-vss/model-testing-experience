"""Error definitions carry no request state; every raise gets a new exception."""

import ast
from pathlib import Path

from testing_agent.core.errors import AppError, ErrBadRequest


def test_error_definition_creates_distinct_exceptions_with_the_same_contract():
    first, second = ErrBadRequest(), ErrBadRequest()
    assert isinstance(first, AppError)
    assert first is not second and first is not ErrBadRequest
    assert (first.code, first.message, first.http_code) == (
        ErrBadRequest.code,
        ErrBadRequest.message,
        ErrBadRequest.http_code,
    )
    try:
        raise first
    except AppError:
        pass
    assert first.__traceback__ is not None
    assert second.__traceback__ is None
    assert ErrBadRequest.__traceback__ is None


def test_application_never_raises_a_shared_error_definition():
    source = Path(__file__).parents[1] / "src" / "testing_agent"
    offenders = []
    for path in source.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Raise)
                and isinstance(node.exc, ast.Name)
                and node.exc.id.startswith("Err")
            ):
                offenders.append(f"{path.relative_to(source)}:{node.lineno}")
    assert not offenders, offenders
