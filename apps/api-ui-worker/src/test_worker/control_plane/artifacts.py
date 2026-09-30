"""Publish execution artifacts to S3 before reporting stable references."""

import hashlib
from pathlib import Path

import httpx


class ArtifactUploader:
    def __init__(self, config, request):
        self.config, self.request = config, request
        self.uploaded = {}

    def publish(self, task_id, value):
        if isinstance(value, list):
            return [self.publish(task_id, item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            if key in {"screenshotPath", "tracePath"} and item:
                result[key] = self.upload(task_id, item)
            else:
                result[key] = self.publish(task_id, item)
        return result

    def upload(self, task_id, local_path):
        path = Path(local_path).resolve()
        if (
            not path.is_relative_to(Path(self.config.artifacts_root_dir).resolve())
            or not path.is_file()
        ):
            raise ValueError("Artifact is missing or outside the task workspace")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        key = (task_id, str(path), digest.hexdigest())
        if key in self.uploaded:
            return self.uploaded[key]
        endpoint = f"/internal/ui-worker/tasks/{task_id}/files"
        ticket = self.request(
            "POST",
            endpoint + "/uploads",
            {
                "workerId": self.config.worker_id,
                "filename": path.name,
                "size": path.stat().st_size,
                "sha256": key[2],
            },
        )
        try:
            with httpx.Client(timeout=300) as storage, path.open("rb") as source:
                response = storage.post(
                    ticket["upload"]["url"],
                    data=ticket["upload"]["fields"],
                    files={"file": (path.name, source)},
                )
                if not response.is_success:
                    raise ValueError("Artifact S3 upload failed")
        except httpx.HTTPError:
            raise ValueError("Artifact S3 upload transport failure") from None
        completed = self.request(
            "POST",
            endpoint + f"/{ticket['fileId']}/complete",
            {"workerId": self.config.worker_id},
        )
        self.uploaded[key] = completed["path"]
        return completed["path"]

    def cleanup(self, task_id):
        # Only remove verified uploads after the platform accepts the final result.
        for key in list(self.uploaded):
            if key[0] == task_id:
                Path(key[1]).unlink(missing_ok=True)
                del self.uploaded[key]
