"""The five charts carry one copy of the shared helpers; these checks keep that true."""

import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHARTS = ROOT / "deploy" / "helm" / "charts"
CHART_NAMES = ("ai-worker", "api-ui-worker", "control-plane", "integration-worker", "studio")


def _template(chart: str, *set_values: str) -> str:
    result = subprocess.run(
        ["helm", "template", "test", str(CHARTS / chart), *set_values],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"helm template {chart} failed:\n{result.stderr}")
    return result.stdout


class HelmChartTests(unittest.TestCase):
    def test_every_chart_carries_the_same_helpers(self):
        # Only the chart's own name may differ between the five copies.
        helpers = {
            chart: (CHARTS / chart / "templates" / "_helpers.tpl")
            .read_text(encoding="utf-8")
            .replace(chart, "CHART")
            for chart in CHART_NAMES
        }

        self.assertEqual(1, len(set(helpers.values())), "templates/_helpers.tpl drifted")

    def test_templates_only_include_their_own_helpers(self):
        # A copied block that still names another chart renders nothing or the wrong thing.
        for chart in CHART_NAMES:
            for path in sorted((CHARTS / chart / "templates").iterdir()):
                for name in re.findall(r'include "([^"]+)"', path.read_text(encoding="utf-8")):
                    self.assertTrue(
                        name.startswith(f"{chart}."),
                        f"{path.relative_to(ROOT)} includes {name}",
                    )

    @unittest.skipUnless(shutil.which("helm"), "helm is not installed")
    def test_every_chart_renders_with_its_defaults(self):
        # ai-worker keeps a stable per-replica identity, so it is a StatefulSet.
        workload = {"ai-worker": "StatefulSet"}
        for chart in CHART_NAMES:
            with self.subTest(chart=chart):
                self.assertIn(f"kind: {workload.get(chart, 'Deployment')}", _template(chart))

    @unittest.skipUnless(shutil.which("helm"), "helm is not installed")
    def test_control_plane_migration_switch_gates_the_config_copy_too(self):
        enabled = _template("control-plane")
        disabled = _template("control-plane", "--set", "migration.enabled=false")

        self.assertIn("kind: ConfigMap", enabled.split("migrate-config-configmap.yaml")[1])
        # The copy only feeds the hook Job, so it must not outlive the switch either.
        self.assertNotIn("kind: ConfigMap", disabled.split("migrate-config-configmap.yaml")[1])

    @unittest.skipUnless(shutil.which("helm"), "helm is not installed")
    def test_ai_worker_config_stays_inside_what_the_worker_reads(self):
        config = _template("ai-worker")

        # Every replica must answer under its own id: the control plane checks ownership by it.
        self.assertIn('worker_id = ""', config)
        self.assertIn("traceable_review_concurrency = 4", config)
        self.assertIn("traceable_review_global_concurrency = 4", config)
        self.assertNotIn("task_claim_path", config)


if __name__ == "__main__":
    unittest.main()
