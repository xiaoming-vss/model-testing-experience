import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("manage", ROOT / "scripts/manage.py")
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(
            ROOT / "config",
            self.root / "config",
            ignore=shutil.ignore_patterns("platform.toml"),
        )
        shutil.copy2(ROOT / "compose.yaml", self.root / "compose.yaml")
        for name, project in manage.PROJECTS.items():
            src = ROOT / project
            dst = self.root / project
            dst.mkdir(parents=True)
            if (src / "config").exists():
                shutil.copytree(
                    src / "config",
                    dst / "config",
                    ignore=shutil.ignore_patterns(
                        "local.toml", "worker.toml", "zentao.toml"
                    ),
                )
            if (src / "config.example.toml").exists():
                shutil.copy2(src / "config.example.toml", dst / "config.example.toml")
        manage.init(self.root)
        self.data = manage.read(self.root / "config/platform.toml")

    def test_init_preserves_credentials(self):
        before = (self.root / "config/platform.toml").read_bytes()
        manage.init(self.root)
        self.assertEqual(before, (self.root / "config/platform.toml").read_bytes())
        keys = [
            self.data["shared"][k]
            for k in ("worker_token", "jwt_key", "integration_key")
        ]
        self.assertEqual(len(set(keys)), 3)

    def test_routes_credentials_and_overrides(self):
        self.data["shared"]["control_plane_port"] = 19000
        self.data["shared"]["public_host"] = "testing.example.com"
        self.data["ai_worker"]["worker"]["max_concurrent_tasks"] = 7
        for mode in ("local", "docker"):
            configs = manage.configurations(self.data, mode, self.root)
            cp = configs["control-plane"]
            self.assertEqual(
                cp["security"]["worker"]["key"],
                configs["ai-worker"]["platform"]["worker_token"],
            )
            self.assertEqual(
                cp["security"]["worker"]["key"],
                configs["api-ui-worker"]["control_plane"]["worker_token"],
            )
            url = (
                "http://control-plane:9000"
                if mode == "docker"
                else "http://127.0.0.1:19000"
            )
            self.assertEqual(configs["ai-worker"]["platform"]["base_url"], url)
            self.assertEqual(configs["api-ui-worker"]["control_plane"]["base_url"], url)
            self.assertEqual(
                configs["api-ui-worker"]["ui"]["artifacts_base_url"],
                "http://testing.example.com:9010",
            )
            self.assertEqual(configs["ai-worker"]["worker"]["max_concurrent_tasks"], 7)
            for config in configs.values():
                self.assertEqual(tomllib.loads(manage.toml_text(config)), config)

    def test_special_characters_in_secrets(self):
        password = "a$b'c\\d@:/?# space"
        self.data["database"]["password"] = password
        manage.write(self.root / "config/platform.toml", manage.toml_text(self.data))
        manage.configure("docker", self.root)
        cp = manage.read(self.root / ".runtime/docker/control-plane.toml")
        self.assertIn(manage.quote(password, safe=""), cp["data"]["db"]["user"]["dsn"])
        if shutil.which("docker"):
            import json

            output = subprocess.check_output(
                manage.compose_command(self.root) + ["config", "--format", "json"],
                text=True,
            )
            rendered = json.loads(output)
            # Compose escapes literal dollars in its reusable config output.
            self.assertEqual(
                rendered["services"]["mysql"]["environment"]["MYSQL_PASSWORD"].replace(
                    "$$", "$"
                ),
                password,
            )

    def test_modes_do_not_overwrite_each_other(self):
        manage.configure("local", self.root)
        local = self.root / manage.PROJECTS["control-plane"] / "config/local.toml"
        before = local.read_bytes()
        manage.configure("docker", self.root)
        self.assertEqual(local.read_bytes(), before)
        self.assertEqual((self.root / ".runtime").stat().st_mode & 0o777, 0o700)

    def test_compose_global_options_are_forwarded(self):
        with (
            patch.object(
                manage.sys,
                "argv",
                ["manage.py", "compose", "-p", "isolated-check", "config", "--quiet"],
            ),
            patch.object(manage, "configure") as configure,
            patch.object(manage.subprocess, "call", return_value=0) as call,
        ):
            with self.assertRaises(SystemExit) as result:
                manage.main()
        self.assertEqual(result.exception.code, 0)
        configure.assert_called_once_with("docker")
        self.assertEqual(
            call.call_args.args[0][-4:], ["-p", "isolated-check", "config", "--quiet"]
        )

    def test_duplicate_ports_rejected(self):
        self.data["shared"]["studio_port"] = self.data["shared"]["mysql_port"]
        with self.assertRaises(ValueError):
            manage.configurations(self.data, "docker", self.root)


if __name__ == "__main__":
    unittest.main()
