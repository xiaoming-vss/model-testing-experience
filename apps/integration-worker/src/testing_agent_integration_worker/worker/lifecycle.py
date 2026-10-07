import json
import os
import tempfile
import time
from pathlib import Path


class Health:
    def __init__(self, path: Path):
        self.path = path
        self.last_progress = 0.0

    def progress(self) -> None:
        self.last_progress = time.time()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump({"pid": os.getpid(), "progressAt": self.last_progress}, stream)
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def stop(self) -> None:
        self.path.unlink(missing_ok=True)


def healthy(path: Path, max_age: float) -> bool:
    try:
        data = json.loads(path.read_text())
        os.kill(int(data["pid"]), 0)
        return 0 <= time.time() - float(data["progressAt"]) <= max_age
    except (OSError, ValueError, KeyError, TypeError):
        return False
