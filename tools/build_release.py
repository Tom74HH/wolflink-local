"""Build the manual installation package from an explicit, public file list."""

import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile


def package_files(root):
    component = root / "custom_components/wolflink_local"
    for path in sorted(component.rglob("*")):
        relative = path.relative_to(component)
        allowed = (
            len(relative.parts) == 1
            and path.suffix == ".py"
            or relative.as_posix()
            in {
                "manifest.json",
                "strings.json",
                "services.yaml",
                "brand/icon.png",
                "brand/icon.svg",
                "frontend/plant-schema.svg",
                "brand/mdi-fire.svg",
                "brand/MDI-LICENSE.txt",
                "brand/LICENSE.Apache-2.0.txt",
                "brand/mdi-fire-SOURCE.json",
                "frontend/dashboard.json",
                "frontend/wolflink-mode-popup.js",
                "README.md",
                "INSTALLATION.md",
                "BESCHREIBUNG.md",
                "LICENSE",
                "NOTICE",
                "WOLF-SCHEMA-QUELLE.json",
                "local/client-cert.pem",
                "local/client-key.pem",
                "local/parameters.json",
                "local/LICENSE.GPL-3.0",
                "local/SOURCE.json",
            }
            or len(relative.parts) == 2
            and relative.parts[0] == "translations"
            and path.suffix == ".json"
        )
        if path.is_file() and allowed:
            yield path.relative_to(root).as_posix(), path


def build(root=None):
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    component = root / "custom_components/wolflink_local"
    version = json.loads((component / "manifest.json").read_text(encoding="utf8"))[
        "version"
    ]
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+(?:\.?[A-Za-z]+[0-9]+)?", version):
        raise ValueError("Invalid release version")
    constants = ast.parse((component / "const.py").read_text(encoding="utf8"))
    actual = next(
        ast.literal_eval(node.value)
        for node in constants.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "VERSION" for t in node.targets)
    )
    if actual != version:
        raise ValueError("Manifest and const.py versions differ")
    files = sorted([*package_files(root), *((name, component / name) for name in ("INSTALLATION.md", "BESCHREIBUNG.md"))])
    for _, source in files:
        if not source.is_file():
            raise FileNotFoundError(source)
    output = root / "dist" / f"WolfLink-local-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    temporary = output.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(
            temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9
        ) as package:
            for name, source in files:
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                package.writestr(info, source.read_bytes())
        with zipfile.ZipFile(temporary) as package:
            if package.testzip() is not None:
                raise ValueError("Invalid release archive")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(
        f"{checksum}  {output.name}\n", encoding="utf8"
    )
    return output


if __name__ == "__main__":
    print(build())
