import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ContainerPinTests(unittest.TestCase):
    def test_k6_image_matches_the_platform_expected_version(self) -> None:
        dockerfile = (ROOT / "apps/perf-worker/Dockerfile").read_text(encoding="utf-8")
        image = re.search(r"^FROM grafana/k6:([^@\s]+)@", dockerfile, re.MULTILINE)

        self.assertIsNotNone(image)
        platform = tomllib.loads(
            (ROOT / "config/platform.example.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(platform["perf_worker"]["k6"]["expected_version"], image.group(1))


if __name__ == "__main__":
    unittest.main()
