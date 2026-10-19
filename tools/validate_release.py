"""Offline release structure checks, including the actual manifest and translations."""

import argparse
import ast
import json
import runpy
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-hacs-repository", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    component = root / "custom_components/wolflink_local"
    required = (
        "__init__.py",
        "dashboard.py",
        "local_api.py",
        "local_programs.py",
        "NOTICE",
        "LICENSE",
        "WOLF-SCHEMA-QUELLE.json",
        "local/SOURCE.json",
        "local/parameters.json",
        "local/client-cert.pem",
        "local/client-key.pem",
        "local/LICENSE.GPL-3.0",
        "frontend/dashboard.json",
        "frontend/wolflink-mode-popup.js",
        "README.md",
        "INSTALLATION.md",
        "BESCHREIBUNG.md",
        "config_flow.py",
        "coordinator.py",
        "sensor.py",
        "select.py",
        "number.py",
        "switch.py",
        "button.py",
        "datetime.py",
        "mode_drafts.py",
        "timed_modes.py",
        "api.py",
        "models.py",
        "controls.py",
        "entity.py",
        "future.py",
        "diagnostics.py",
        "time_program.py",
        "services.py",
        "services.yaml",
        "manifest.json",
        "strings.json",
        "translations/de.json",
        "translations/en.json",
        "brand/icon.png",
    )
    for file in required:
        if not (component / file).is_file():
            raise SystemExit(f"Missing runtime file: {file}")
    manifest = json.loads((component / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["domain"] == "wolflink_local"
    assert manifest["version"] == runpy.run_path(str(component / "const.py"))["VERSION"]
    assert manifest["requirements"] == []
    assert manifest["iot_class"] == "local_polling"
    assert manifest["name"] == "WolfLink local"
    assert manifest["config_flow"] is True
    for file in component.rglob("*.py"):
        ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
    for file in component.rglob("*.json"):
        json.loads(file.read_text(encoding="utf-8"))
    strings = json.loads((component / "strings.json").read_text(encoding="utf-8"))
    en = json.loads((component / "translations/en.json").read_text(encoding="utf-8"))
    de = json.loads((component / "translations/de.json").read_text(encoding="utf-8"))
    assert strings == en

    def keys(value):
        return (
            {k: keys(v) for k, v in value.items()} if isinstance(value, dict) else None
        )

    assert keys(de) == keys(en), "Translation keys differ"
    assert len(strings["entity"]["select"]) == 4
    assert len(strings["entity"]["number"]) == 4
    hacs = json.loads((root / "hacs.json").read_text(encoding="utf-8"))
    assert hacs["homeassistant"] == "2026.10.1"
    assert (root / "LICENSE").is_file() and (root / "NOTICE").is_file()
    if args.require_hacs_repository:
        assert manifest.get("issue_tracker", "").startswith("https://github.com/"), (
            "Configure real repository links first"
        )
        assert manifest["documentation"].endswith("#readme")
    print(
        f"Runtime structure, Python syntax, JSON and translations valid for {manifest['version']}."
    )
    print(
        "HACS repository links: "
        + (
            "configured"
            if manifest.get("issue_tracker")
            else "pending; direct installation is available"
        )
    )


if __name__ == "__main__":
    main()
