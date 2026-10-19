"""Packaging must be repeatable and must exclude private development material."""

from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.build_release import build


class BuildReleaseTests(unittest.TestCase):
    def test_repeatable_package_with_public_files_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("README.md", "frontend/dashboard-smartset.yaml"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("synthetic public file", encoding="utf8")
            component = root / "custom_components/wolflink_local"
            component.mkdir(parents=True, exist_ok=True)
            for name in ("INSTALLATION.md", "BESCHREIBUNG.md", "CHANGELOG.md", "TESTHINWEISE.md"):
                (component / name).write_text("synthetic public instructions", encoding="utf8")
            assets = component / "frontend"
            assets.mkdir()
            (assets / "wolflink-mode-popup.js").write_text("// bundled UI")
            (assets / "dashboard.json").write_text("{}")
            (component / "manifest.json").write_text(
                '{"version":"0.2.0.dev11"}', encoding="utf8"
            )
            (component / "const.py").write_text(
                'VERSION = "0.2.0.dev11"', encoding="utf8"
            )
            (component / "private-diagnostics.json").write_text(
                "PRIVATE", encoding="utf8"
            )
            (root / "wolf-diagnostics.json").write_text("PRIVATE", encoding="utf8")
            (root / "frontend/wolflink-mode-popup.js").write_text(
                "// synthetic module", encoding="utf8"
            )
            output = build(root)
            first = output.read_bytes()
            self.assertEqual(build(root).read_bytes(), first)
            with zipfile.ZipFile(output) as package:
                self.assertIn(
                    "custom_components/wolflink_local/frontend/wolflink-mode-popup.js",
                    package.namelist(),
                )
                self.assertTrue(
                    all(
                        name.startswith("custom_components/wolflink_local/")
                        or name in ("INSTALLATION.md", "BESCHREIBUNG.md", "CHANGELOG.md", "TESTHINWEISE.md")
                        for name in package.namelist()
                    )
                )
                for name in ("INSTALLATION.md", "BESCHREIBUNG.md", "CHANGELOG.md", "TESTHINWEISE.md"):
                    self.assertEqual(package.read(name), package.read("custom_components/wolflink_local/" + name))
                self.assertFalse(
                    any("diagnostics" in name for name in package.namelist())
                )
                self.assertNotIn(
                    b"PRIVATE",
                    b"".join(package.read(name) for name in package.namelist()),
                )
            self.assertTrue(output.with_suffix(".zip.sha256").is_file())


if __name__ == "__main__":
    unittest.main()
