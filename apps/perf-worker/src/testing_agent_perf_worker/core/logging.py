"""Safe logging setup.

Worker logs must only contain identifiers, statuses and timing. Request bodies,
environment values, remote-write credentials and control-plane tokens are never
logged by this module; call sites are responsible for keeping their fields safe.
"""

from __future__ import annotations

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    """Configure stderr logging without leaking third-party request details."""

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
        stream=sys.stderr,
    )
    # httpx/httpcore exception text can include signed URLs or authorization
    # material. Keep their own request logs quiet; our call sites log only safe
    # identifiers and status codes.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
