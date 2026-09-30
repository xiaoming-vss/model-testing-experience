import tarfile
from pathlib import PurePosixPath

from testing_agent.core.errors import ErrBadRequest
from testing_agent.services.ai_source_archive import (
    _canonical_archive_path,
    validate_source_archive,
)


def validate_skill_archive(filename, stream):
    if PurePosixPath(filename).suffix.lower() == ".zip":
        return validate_source_archive(filename, stream)
    try:
        with tarfile.open(fileobj=stream, mode="r:") as archive:
            names, size = set(), 0
            for member in archive:
                name = _canonical_archive_path(member.name)
                if name in names or not (member.isfile() or member.isdir()):
                    raise ErrBadRequest
                names.add(name)
                size += member.size
                if len(names) > 50000 or size > 1024 * 1024 * 1024:
                    raise ErrBadRequest
    except (tarfile.TarError, OSError, ValueError):
        raise ErrBadRequest from None
