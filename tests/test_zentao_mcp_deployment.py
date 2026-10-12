"""Validate copied deployment files without starting any service."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "deploy/zentao-mcp"
TEMPLATE_FILES = (
    "compose.yaml", "config.example.yaml", "README.md",
    "compose.bug-options.yaml", "enable-bug-options.py",
    "zentao-22.6-api-form-uid.patch",
)


def prepare_deployment(directory, name="mtx-zentao-project-a", port=9091):
    directory.mkdir(parents=True)
    for filename in TEMPLATE_FILES:
        shutil.copy2(TEMPLATE / filename, directory / filename)
    compose = directory / "compose.yaml"
    compose.write_text(
        compose.read_text()
        .replace("mtx-zentao-project-a", name)
        .replace(":-9091", f":-{port}")
    )
    (directory / "config").mkdir()
    shutil.copy2(directory / "config.example.yaml", directory / "config/config.yaml")
    return directory


def compose_command(directory, *args):
    return [
        "docker",
        "compose",
        "--env-file",
        "/dev/null",
        "-f",
        str(directory / "compose.yaml"),
        *args,
    ]


def compose_environment():
    # Ignore ambient overrides so these tests always validate the copied defaults.
    return {
        key: value for key, value in os.environ.items() if not key.startswith("MCP_")
    }


@unittest.skipUnless(
    shutil.which("docker"), "Docker CLI required to validate Compose files"
)
class ZentaoMcpDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def render(self, directory):
        return json.loads(
            subprocess.check_output(
                compose_command(directory, "config", "--format", "json"),
                env=compose_environment(),
            )
        )

    def test_copied_files_use_published_image_and_local_readonly_config(self):
        directory = prepare_deployment(self.root / "standalone")
        rendered = self.render(directory)
        service = rendered["services"]["zentao-mcp"]
        self.assertNotIn("build", service)
        self.assertIn("xiaoming-x/zentao-mcp:2026-10-04-attachments@sha256:", service["image"])
        mount = service["volumes"][0]
        self.assertEqual(mount["source"], str(directory / "config"))
        self.assertTrue(mount["read_only"])
        self.assertFalse(mount["bind"]["create_host_path"])
        self.assertNotIn(str(ROOT), json.dumps(rendered))
        self.assertEqual(
            set(path.name for path in TEMPLATE.iterdir() if path.is_file()),
            set(TEMPLATE_FILES) | {".gitattributes"}
        )

    def test_two_copies_use_independent_projects_ports_configs_and_networks(self):
        first = self.render(prepare_deployment(self.root / "a"))
        second = self.render(
            prepare_deployment(self.root / "b", "mtx-zentao-project-b", 9092)
        )
        self.assertNotEqual(first["name"], second["name"])
        left, right = (item["services"]["zentao-mcp"] for item in (first, second))
        self.assertNotEqual(left["container_name"], right["container_name"])
        self.assertNotEqual(
            left["ports"][0]["published"], right["ports"][0]["published"]
        )
        self.assertNotEqual(left["volumes"][0]["source"], right["volumes"][0]["source"])
        self.assertNotEqual(
            first["networks"]["mcp"]["name"], second["networks"]["mcp"]["name"]
        )
        self.assertEqual(left["image"], right["image"])

    def test_bug_options_overlay_mounts_the_generated_schema_readonly(self):
        directory = prepare_deployment(self.root / "options")
        (directory / "config/bug-options-openapi.json").write_text("{}")
        command = compose_command(directory, "-f", str(directory / "compose.bug-options.yaml"),
                                  "config", "--format", "json")
        rendered = json.loads(subprocess.check_output(command, env=compose_environment()))
        service = rendered["services"]["zentao-mcp"]
        schema = next(m for m in service["volumes"] if m["target"] == "/config/zentao-openapi.json")
        self.assertEqual(schema["source"], str(directory / "config/bug-options-openapi.json"))
        self.assertTrue(schema["read_only"])
        self.assertFalse(schema["bind"]["create_host_path"])
        self.assertEqual(service["image"], self.render(directory)["services"]["zentao-mcp"]["image"])

    def test_private_shared_network_can_be_configured_without_published_ports(self):
        directory = prepare_deployment(self.root / "internal")
        compose = directory / "compose.yaml"
        compose.write_text(
            compose.read_text()
            .replace(
                '    ports:\n      - "${MCP_BIND_HOST:-127.0.0.1}:${MCP_HOST_PORT:-9091}:9090"\n',
                "",
            )
            .replace(
                "${MCP_NETWORK:-${MCP_PROJECT_NAME:-mtx-zentao-project-a}}",
                "mtx_default",
            )
            .replace("${MCP_EXTERNAL_NETWORK:-false}", "true")
        )
        rendered = self.render(directory)
        self.assertFalse(rendered["services"]["zentao-mcp"].get("ports"))
        self.assertEqual(rendered["networks"]["mcp"]["name"], "mtx_default")
        self.assertTrue(rendered["networks"]["mcp"]["external"])
