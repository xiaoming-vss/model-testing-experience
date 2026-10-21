import importlib.util
import json
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
        shutil.copytree(ROOT / "deploy", self.root / "deploy")
        for name, project in manage.PROJECTS.items():
            src = ROOT / project
            dst = self.root / project
            dst.mkdir(parents=True)
            if (src / "config").exists():
                shutil.copytree(
                    src / "config",
                    dst / "config",
                    ignore=shutil.ignore_patterns(
                        "local.toml", "worker.toml"
                    ),
                )
            if (src / "config.example.toml").exists():
                shutil.copy2(src / "config.example.toml", dst / "config.example.toml")
        manage.init(self.root)
        self.data = manage.read(self.root / "config/platform.toml")

    def test_ai_worker_selection_renders_only_one_service_and_isolated_storage(self):
        for backend, project, volume in (
            ("nanobot", "ai-worker", "ai-runtime"),
            ("pi", "ai-worker-pi", "ai-pi-runtime"),
        ):
            with self.subTest(backend=backend):
                self.data.setdefault("ai_worker", {})["agent"] = {"backend": backend}
                manage.write(self.root / "config/platform.toml", manage.toml_text(self.data))
                manage.configure("docker", self.root)
                rendered = json.loads(subprocess.check_output(
                    manage.compose_command(self.root) + ["config", "--format", "json"],
                    text=True,
                ))
                self.assertNotIn("ai-worker-pi", rendered["services"])
                worker = rendered["services"]["ai-worker"]
                self.assertEqual(worker["image"], f"mtx/{project}:local")
                self.assertEqual(Path(worker["build"]["context"]), self.root / "apps" / project)
                self.assertEqual(next(v["source"] for v in worker["volumes"]
                                      if v["target"] == "/data/runtime"), volume)
                self.assertEqual(next(v["source"] for v in worker["volumes"]
                                      if v["target"] == "/app/config/worker.toml"),
                                 str(self.root / ".runtime/docker" / f"{project}.toml"))
                config = manage.read(self.root / ".runtime/docker" / f"{project}.toml")
                self.assertEqual(config["platform"]["worker_token"], self.data["shared"]["worker_token"])
                self.assertNotIn("agent", config)

    def test_legacy_ai_selection_defaults_to_nanobot_and_rejects_typos(self):
        self.data["ai_worker"].pop("agent", None)
        self.assertEqual(manage.selected_ai_worker(self.data), "ai-worker")
        self.data["ai_worker"]["agent"] = {"backend": "typo"}
        with self.assertRaisesRegex(ValueError, "backend"):
            manage.configurations(self.data, "docker", self.root)

    def test_pi_local_configuration_is_independent(self):
        self.data["ai_worker_pi"]["pi"]["run_timeout_seconds"] = 42
        configs = manage.configurations(self.data, "local", self.root)
        self.assertEqual(configs["ai-worker-pi"]["pi"]["run_timeout_seconds"], 42)
        self.assertNotIn("pi", configs["ai-worker"])
        self.assertNotIn("nanobot", configs["ai-worker-pi"])

    def test_asset_import_limits_are_generated_for_both_modes(self):
        self.data["control_plane"]["asset_import"]["max_items"] = 123
        for mode in ("local", "docker"):
            config = manage.configurations(self.data, mode, self.root)["control-plane"]
            self.assertEqual(config["asset_import"]["max_items"], 123)
            self.assertEqual(config["asset_import"]["max_concurrent"], 2)

    def test_ldap_legacy_file_settings_are_not_generated(self):
        self.assertNotIn("ldap", self.data["control_plane"]["security"])
        self.data["control_plane"]["security"]["ldap"] = {
            "enabled": True, "bind_password": "legacy-secret", "tls_ca_file": "missing.pem"
        }
        manage.write(self.root / "config/platform.toml", manage.toml_text(self.data))
        manage.upgrade_config(self.root)
        for mode in ("local", "docker"):
            config = manage.configurations(self.data, mode, self.root)["control-plane"]
            self.assertNotIn("ldap", config["security"])
        override = self.root / ".runtime/compose.ldap-ca.json"
        override.parent.mkdir(exist_ok=True)
        override.write_text("{}")
        manage.configure("docker", self.root)
        self.assertFalse(override.exists())

    def test_mysql_slow_log_is_generated_and_configurable(self):
        manage.configure("docker", self.root)
        env = (self.root / ".runtime/compose.env").read_text()
        self.assertIn("MYSQL_SLOW_QUERY_LOG='1'", env)
        self.assertIn("MYSQL_LONG_QUERY_TIME='0.5'", env)
        self.data["database"].update(slow_query_log=False, long_query_time=1.25)
        manage.write(self.root / "config/platform.toml", manage.toml_text(self.data))
        manage.configure("docker", self.root)
        env = (self.root / ".runtime/compose.env").read_text()
        self.assertIn("MYSQL_SLOW_QUERY_LOG='0'", env)
        self.assertIn("MYSQL_LONG_QUERY_TIME='1.25'", env)

    def test_mysql_slow_log_rejects_invalid_values(self):
        for value in (0, -1, float("nan"), float("inf"), "0.5", True):
            self.data["database"]["long_query_time"] = value
            with self.assertRaisesRegex(ValueError, "long_query_time"):
                manage.validate(self.data)
        self.data["database"]["long_query_time"] = 0.5
        self.data["database"]["slow_query_log"] = "yes"
        with self.assertRaisesRegex(ValueError, "slow_query_log"):
            manage.validate(self.data)

    def test_init_preserves_credentials(self):
        before = (self.root / "config/platform.toml").read_bytes()
        manage.init(self.root)
        self.assertEqual(before, (self.root / "config/platform.toml").read_bytes())
        keys = [
            self.data["shared"][k]
            for k in ("worker_token", "jwt_key", "integration_key")
        ]
        self.assertEqual(len(set(keys)), 3)

    def test_integration_config_upgrade_preserves_custom_values_permissions_and_secrets(self):
        path = self.root / "config/platform.toml"
        old = manage.read(path)
        old["shared"].pop("integration_worker_token")
        old["shared"].pop("integration_runtime_generation")
        old["control_plane"]["integration_execution"] = {"project_ids": ["pilot"], "lease_seconds": 75}
        old["custom"] = {"keep": "value"}
        manage.write(path, manage.toml_text(old), permissions=0o640)
        manage.upgrade_config(self.root)
        upgraded = manage.read(path)
        self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        for key, value in old["shared"].items():
            self.assertEqual(upgraded["shared"][key], value)
        self.assertEqual(upgraded["custom"], old["custom"])
        self.assertNotEqual(upgraded["shared"]["integration_worker_token"], old["shared"]["worker_token"])
        execution = upgraded["control_plane"]["integration_execution"]
        self.assertEqual(execution["project_ids"], ["pilot"])
        self.assertEqual(execution["lease_seconds"], 75)
        self.assertFalse(execution["enabled"])
        before = path.read_bytes()
        manage.upgrade_config(self.root)
        self.assertEqual(path.read_bytes(), before)

    def test_integration_worker_credentials_are_generated_separately(self):
        for mode in ("local", "docker"):
            configs = manage.configurations(self.data, mode, self.root)
            cp = configs["control-plane"]
            worker = configs["integration-worker"]
            self.assertNotEqual(cp["security"]["integration_worker"]["key"], cp["security"]["worker"]["key"])
            self.assertEqual(worker["control_plane"]["worker_token"],
                             cp["security"]["integration_worker"]["key"])
            self.assertEqual(set(worker), {"control_plane", "worker"})
            self.assertEqual(set(worker["control_plane"]),
                             {"base_url", "worker_token", "timeout_seconds", "retry_attempts"})
            self.assertEqual(worker["control_plane"]["base_url"],
                             configs["api-ui-worker"]["control_plane"]["base_url"])
            runtime = "/app/runtime" if mode == "docker" else "runtime"
            self.assertEqual(worker["worker"]["evidence_file"], runtime + "/evidence.json")
            self.assertEqual(cp["integration_execution"]["runtime_generation"],
                             self.data["shared"]["integration_runtime_generation"])
            self.assertFalse(cp["integration_execution"]["enabled"])
        self.data["shared"]["integration_worker_token"] = self.data["shared"]["worker_token"]
        with self.assertRaisesRegex(ValueError, "must differ"):
            manage.validate(self.data)

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is required")
    def test_integration_worker_has_no_listener_or_shared_outbox(self):
        manage.configure("docker", self.root)
        rendered = json.loads(subprocess.check_output(
            manage.compose_command(self.root) + ["config", "--format", "json"], text=True,
        ))
        worker = rendered["services"]["integration-worker"]
        self.assertFalse(worker.get("ports"))
        self.assertFalse(worker.get("expose"))
        self.assertFalse(worker.get("container_name"))
        self.assertEqual(worker["stop_grace_period"], "3m35s")
        self.assertEqual(set(worker["depends_on"]), {"control-plane"})
        self.assertEqual(worker["depends_on"]["control-plane"]["condition"], "service_healthy")
        runtime = next(item for item in worker["volumes"] if item["target"] == "/app/runtime")
        self.assertEqual(runtime["type"], "volume")
        self.assertNotIn("source", runtime)

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
            self.assertNotIn("artifacts_base_url", configs["api-ui-worker"]["ui"])
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

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is required")
    def test_branding_preserves_legacy_data_and_isolated_deployments(self):
        manage.configure("docker", self.root)
        command = manage.compose_command(self.root)
        normal = json.loads(
            subprocess.check_output(command + ["config", "--format", "json"], text=True)
        )
        self.assertEqual(normal["name"], "mtx")
        isolated = json.loads(
            subprocess.check_output(
                command + ["-p", "mtx-isolated-check", "config", "--format", "json"],
                text=True,
            )
        )
        legacy = json.loads(
            subprocess.check_output(
                command
                + [
                    "-f",
                    str(self.root / "deploy/compose.legacy-data.yaml"),
                    "config",
                    "--format",
                    "json",
                ],
                text=True,
            )
        )
        for volume in normal["volumes"]:
            self.assertEqual(normal["volumes"][volume]["name"], f"mtx_{volume}")
            self.assertEqual(
                isolated["volumes"][volume]["name"], f"mtx-isolated-check_{volume}"
            )
            self.assertEqual(
                legacy["volumes"][volume]["name"], f"testing-agent_{volume}"
            )
            self.assertTrue(legacy["volumes"][volume]["external"])

    def test_duplicate_ports_rejected(self):
        self.data["shared"]["studio_port"] = self.data["shared"]["mysql_port"]
        with self.assertRaises(ValueError):
            manage.configurations(self.data, "docker", self.root)

    def test_external_url_works_without_bundled_database_settings(self):
        url = "mysql://app:p%40ss%23word@[::1]:3306/existing?charset=utf8mb4"
        self.data["database"] = {"url": url}
        del self.data["shared"]["mysql_port"]
        manage.write(self.root / "config/platform.toml", manage.toml_text(self.data))
        for mode in ("local", "docker"):
            manage.configure(mode, self.root)
            config = manage.configurations(self.data, mode, self.root)
            self.assertEqual(
                config["control-plane"]["data"]["db"]["user"]["dsn"],
                url.replace("mysql://", "mysql+asyncmy://", 1),
            )
        self.assertNotIn("p%40ss", (self.root / ".runtime/compose.env").read_text())

    def test_invalid_database_urls_do_not_expose_credentials(self):
        for url in (
            "postgresql://app:secret@localhost/db",
            "mysql://app:secret@localhost",
            "mysql://app:secret@localhost:99999/db",
            "mysql://app:secret@/db",
            "mysql://app:secret@localhost/db#fragment",
            "mysql://app:secret@local host/db",
        ):
            with self.subTest(url=url):
                self.data["database"]["url"] = url
                with self.assertRaises(ValueError) as result:
                    manage.configurations(self.data, "local", self.root)
                self.assertNotIn("secret", str(result.exception))

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is required")
    def test_external_compose_skips_mysql_and_automatic_migration(self):
        self.data["database"]["url"] = "mysql+asyncmy://app:secret@db.example.com/db"
        manage.write(self.root / "config/platform.toml", manage.toml_text(self.data))
        manage.configure("docker", self.root)
        command = manage.compose_command(self.root)

        def render(options=()):
            return json.loads(
                subprocess.check_output(
                    command + list(options) + ["config", "--format", "json"], text=True
                )
            )

        normal = render()
        self.assertNotIn("mysql", normal["services"])
        self.assertNotIn("migrate", normal["services"])
        self.assertNotIn("mysql-data", normal["volumes"])
        self.assertEqual(
            set(normal["services"]["control-plane"].get("depends_on", {})), set()
        )
        migration = render(["--profile", "migration"])
        self.assertIn("migrate", migration["services"])
        self.assertFalse(migration["services"]["migrate"].get("depends_on"))
        self.data["database"]["url"] = ""
        manage.write(self.root / "config/platform.toml", manage.toml_text(self.data))
        manage.configure("docker", self.root)
        command = manage.compose_command(self.root)
        bundled = render()
        self.assertIn("mysql", bundled["services"])
        self.assertIn("migrate", bundled["services"]["control-plane"]["depends_on"])


if __name__ == "__main__":
    unittest.main()
