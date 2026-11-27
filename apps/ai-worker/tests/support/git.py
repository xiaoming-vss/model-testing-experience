"""Git stand-ins for workspace tests; no collected cases."""

from pathlib import Path

from testing_agent_ai_worker.models.task import GitlabCredentials
from testing_agent_ai_worker.tasks.git_workspace import GitWorkspaceError


def credentials(token: str = "secret-token-1") -> list[GitlabCredentials]:
    """GitLab credentials of ``repo-1`` reached with ``token``."""
    return [
        GitlabCredentials(
            connection_id="conn-1",
            base_url="https://gitlab.example.com",
            access_token=token,
            repository_ids=["repo-1"],
        )
    ]


class FakeGitRunner:
    """Git stand-in: ``clone`` materializes the configured tree and ``rev-parse`` returns ``head``.

    ``files`` maps paths to contents and ``directories`` are created empty. A clone whose source
    contains ``fail_clone`` raises instead, and a diff command returns ``diff``. ``calls`` records
    every call; ``all_args`` joins their arguments for assertions.
    """

    def __init__(
        self,
        *,
        head: str = "head-sha",
        files: dict[str, str] | None = None,
        directories: tuple[str, ...] = (),
        diff: str = "",
        fail_clone: str | None = None,
    ) -> None:
        self.head = head
        self.files = files or {}
        self.directories = directories
        self.diff = diff
        self.fail_clone = fail_clone
        self.calls: list[dict] = []

    def run(self, args, *, cwd=None, env=None, timeout=300.0):
        self.calls.append(
            {"args": list(args), "cwd": cwd, "env": dict(env or {}), "timeout": timeout}
        )
        return self.answer(args)

    def answer(self, args) -> str:
        """Answer one recorded git command."""
        if args[0] == "clone":
            if self.fail_clone and self.fail_clone in args[-2]:
                raise GitWorkspaceError("clone failed")
            self.materialize(Path(args[-1]))
            return ""
        if args[0] == "rev-parse":
            return f"{self.head}\n"
        if "diff" in args:
            return self.diff
        return ""

    def materialize(self, repo: Path) -> None:
        """Create the configured directories and files in the cloned ``repo``."""
        for name in self.directories:
            (repo / name).mkdir(parents=True, exist_ok=True)
        for name, content in self.files.items():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    def all_args(self) -> str:
        return "\n".join(" ".join(call["args"]) for call in self.calls)
