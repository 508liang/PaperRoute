"""Create the release source archive with an explicit, private-data-free allowlist."""

import base64
import hashlib
import importlib.metadata
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "release" / "PaperRoute-source-0.1.0"
ARCHIVE = DEST.parent / (DEST.name + ".zip")


def private_values():
    values = set()
    gui = ROOT / "config" / "local_gui_config.json"
    if gui.is_file():
        config = json.loads(gui.read_text(encoding="utf-8"))
        for name, value in config.get("api_configs", {}).items():
            if any(word in name.upper() for word in ("KEY", "SECRET", "TOKEN", "PASSWORD")) and value:
                values.add(value)
    models = ROOT / "config" / "local_models.json"
    if models.is_file():
        for profile in json.loads(models.read_text(encoding="utf-8")).get("profiles", []):
            if profile.get("api_key"):
                values.add(profile["api_key"])
    engine = ROOT / "config" / "local_engine_config.json"
    if engine.is_file():
        config = json.loads(engine.read_text(encoding="utf-8"))
        for translator in config.get("translators", []):
            for name, value in translator.get("envs", {}).items():
                if any(word in name.upper() for word in ("KEY", "SECRET", "TOKEN", "PASSWORD")) and isinstance(value, str) and value:
                    values.add(value)
    for value in list(values):
        try:
            values.add(base64.b64decode(value, validate=True).decode("utf-8"))
        except (ValueError, UnicodeError):
            pass
    return [value.encode("utf-8") for value in values if len(value) >= 8]


def main():
    files = [ROOT / name for name in ("README.md", "README_EN.md", "LICENSE", "LICENSE_SCOPE.md", "PUBLISHING.md",
              "THIRD_PARTY_NOTICES.md", "CHANGELOG.md", ".gitignore", "_launcher.py",
              "config/app.json", "config/local_models.example.json", "assets/paperroute.svg", "assets/paperroute.png", "assets/paperroute.ico",
              "assets/chevron-down.svg", "assets/chevron-up.svg", "assets/checkmark.svg", "assets/paperroute-workspace.png")]
    for folder, pattern in (("core/site-packages/pdf2zh", "*.py"), ("launcher_src", "*.cs"), ("launcher_src", "*.manifest"),
                            ("scripts", "*.py"), ("scripts", "*.ps1"), ("tests", "*.py"), ("docs", "*.md"), ("licenses", "*.txt"), ("licenses", "*.rtf")):
        files.extend((ROOT / folder).glob(pattern))
    files = [file for file in files if file.name not in {"zotero_utils.py", "gui.py", "restyle_paperroute.py"}]
    files = sorted(set(files))
    secrets = private_values()
    # Scan before copying; never print a matched secret.
    for file in files:
        data = file.read_bytes()
        if any(value in data for value in secrets):
            raise RuntimeError(f"Export refused: a configured credential matched {file.relative_to(ROOT)}")
    DEST.mkdir(parents=True, exist_ok=True)
    expected = {file.relative_to(ROOT).as_posix() for file in files}
    # Do not silently reuse a directory containing unknown files.
    existing = {file.relative_to(DEST).as_posix() for file in DEST.rglob("*") if file.is_file()}
    if existing - expected - {"SOURCE_MANIFEST.json", "RUNTIME_VERSIONS.json"}:
        raise RuntimeError("The export directory contains unexpected files; choose a new clean destination")
    manifest = []
    for file in files:
        relative = file.relative_to(ROOT)
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
        manifest.append({"path": relative.as_posix(), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    versions = []
    for package in (ROOT / "core" / "site-packages").glob("*.dist-info"):
        distribution = importlib.metadata.PathDistribution(package)
        versions.append({"name": distribution.metadata.get("Name"), "version": distribution.version,
                         "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License", "")[:200]})
    (DEST / "SOURCE_MANIFEST.json").write_text(json.dumps({"project": "PaperRoute", "version": "0.1.0",
         "repository": "https://github.com/508liang/PaperRoute", "upstream_shell_license": "unspecified; see LICENSE_SCOPE.md",
         "files": manifest}, indent=2), encoding="utf-8")
    (DEST / "RUNTIME_VERSIONS.json").write_text(json.dumps(versions, indent=2), encoding="utf-8")
    with zipfile.ZipFile(ARCHIVE, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(DEST.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(DEST.parent))
    with zipfile.ZipFile(ARCHIVE) as archive:
        assert archive.testzip() is None
        for name in archive.namelist():
            assert not any(part in ("local-backup", "logs", "pdf2zh_files", ".verification") for part in Path(name).parts)
            assert not name.endswith(("local_models.json", "local_gui_config.json", "local_history.json", "local_engine_config.json"))
    print(f"Source snapshot: {ARCHIVE.name}; {len(manifest)} source files; credential scan passed")
    print("Third-party license boundaries are retained in LICENSE_SCOPE.md and the notices.")


if __name__ == "__main__":
    main()
