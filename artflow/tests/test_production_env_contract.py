from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class ProductionEnvContractTests(unittest.TestCase):
    """Exercise Compose resolution without reading any real secret files."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="apix-compose-contract-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = Path(__file__).resolve().parents[1] / "docker-compose.yml"
        shutil.copyfile(source, self.root / "docker-compose.yml")
        self.main_env = self.root / ".env"
        # Synthetic fixture only; the production lab file is never accessed.
        self.lab_env = self.root / ".env.neironych"
        self.main_env.write_text("NEIRONYCH_API_KEY=canonical-test-key\n", encoding="utf-8")

    def config(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "docker", "compose", "--project-directory", str(self.root),
                "--env-file", str(self.main_env),
                "-f", str(self.root / "docker-compose.yml"),
                "config", "--format", "json",
            ],
            cwd=self.root,
            env={"PATH": os.environ.get("PATH", os.defpath), "HOME": str(self.root)},
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def app_environment(self) -> dict[str, str]:
        result = self.config()
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["services"]["app"].get("environment", {})

    def test_canonical_key_wins_when_lab_fixture_exists(self) -> None:
        self.lab_env.write_text("NEIRONYCH_API_KEY=lab-test-key\n", encoding="utf-8")
        self.assertEqual(self.app_environment()["NEIRONYCH_API_KEY"], "canonical-test-key")

    def test_lab_fixture_cannot_fill_missing_production_key(self) -> None:
        self.main_env.write_text("ENV=production\n", encoding="utf-8")
        self.lab_env.write_text("NEIRONYCH_API_KEY=lab-test-key\n", encoding="utf-8")
        self.assertNotIn("NEIRONYCH_API_KEY", self.app_environment())

    def test_canonical_env_works_without_lab_file(self) -> None:
        self.assertEqual(self.app_environment()["NEIRONYCH_API_KEY"], "canonical-test-key")

    def test_canonical_env_remains_required(self) -> None:
        self.main_env.unlink()
        self.lab_env.write_text("NEIRONYCH_API_KEY=lab-test-key\n", encoding="utf-8")
        self.assertNotEqual(self.config().returncode, 0)


if __name__ == "__main__":
    unittest.main()
