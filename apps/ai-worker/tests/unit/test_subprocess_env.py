import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from testing_agent_ai_worker.models.task import GitlabCredentials
from testing_agent_ai_worker.tasks.git_workspace import (
    GIT_ENV_ALLOWLIST,
    SubprocessGitRunner,
    git_env,
)


class GitSubprocessEnvironmentTests(unittest.TestCase):
    def test_git_env_and_child_process_exclude_parent_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            binary_dir = root / "bin"
            binary_dir.mkdir()
            fake_git = binary_dir / "git"
            fake_git.write_text("#!/bin/sh\nenv\n", encoding="utf-8")
            fake_git.chmod(fake_git.stat().st_mode | stat.S_IXUSR)

            path_entries = [str(binary_dir), os.environ.get("PATH", "")]
            with patch.dict(
                os.environ,
                {
                    "PATH": os.pathsep.join(path_entries),
                    "TESTING_AGENT_WORKER_TOKEN": "SECRET-MARKER",
                    "AWS_SECRET_ACCESS_KEY": "SECRET-MARKER",
                },
            ):
                env = git_env(
                    root / "auth",
                    GitlabCredentials(
                        connection_id="connection-1",
                        base_url="https://gitlab.example.com",
                        access_token="secret-token",
                        repository_ids=["repository-1"],
                    ),
                )
                output = SubprocessGitRunner().run(["version"], env=env)

            self.assertNotIn("TESTING_AGENT_WORKER_TOKEN", env)
            self.assertNotIn("AWS_SECRET_ACCESS_KEY", env)
            self.assertEqual("secret-token", env["GIT_PASSWORD"])
            self.assertEqual("0", env["GIT_TERMINAL_PROMPT"])
            self.assertEqual(env["HOME"], str(root / "auth" / "home"))
            self.assertIn("PATH", env)
            self.assertEqual(
                [key for key in env if key in GIT_ENV_ALLOWLIST],
                [key for key in GIT_ENV_ALLOWLIST if key in env],
            )
            self.assertNotIn("SECRET-MARKER", output)
            self.assertIn("GIT_PASSWORD=secret-token", output)
            self.assertIn("GIT_TERMINAL_PROMPT=0", output)


if __name__ == "__main__":
    unittest.main()
