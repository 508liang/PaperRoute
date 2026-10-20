"""Build a clean, trimmed offline Windows exe without embedding user data.

Requires the complete local runtime. Keeps third-party attribution and license
scope records; see PUBLISHING.md.
Copyright (C) 2026 PaperRoute contributors. AGPL-3.0-only.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from make_source_bundle import private_values

QT_MODULES = {"QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtSvg", "QtXml", "QtPrintSupport", "QtTest"}
QT_DLLS = {name.replace("Qt", "Qt5", 1) + ".dll" for name in QT_MODULES}
QT_DLLS |= {"d3dcompiler_47.dll", "libEGL.dll", "libGLESv2.dll"}
ROOT_FILES = ["_launcher.py", "README.md", "README_EN.md", "LICENSE", "LICENSE_SCOPE.md", "THIRD_PARTY_NOTICES.md",
              "PUBLISHING.md", "CHANGELOG.md", "config/app.json", "config/local_models.example.json",
              "assets/paperroute.svg", "assets/paperroute.png", "assets/paperroute.ico",
              "assets/chevron-down.svg", "assets/chevron-up.svg", "assets/checkmark.svg", "assets/doclayout_yolo.onnx",
              "assets/paperroute-workspace.png", "docs/ALIYUN.md", "docs/BUILDING.md"]


def runtime_file(path):
    rel = path.relative_to(ROOT)
    parts = rel.parts
    if any(part in {"__pycache__", "tests", "test", ".pytest_cache"} for part in parts):
        return False
    if path.suffix.lower() in {".pyc", ".pyo", ".pyi", ".lib", ".h", ".hpp", ".c", ".cpp", ".pyx", ".pxd"}:
        return False
    if path.name.startswith("test_"):
        return False
    if "pdf2zh" in parts and (path.name.startswith("zotero") or path.name in {"gui.py", "gui_backup.py"}):
        return False
    if "cv2" in parts:
        if path.name.startswith("opencv_videoio_ffmpeg") or "data" in parts:
            return False
    if "PyQt5" in parts:
        qt = parts.index("PyQt5")
        sub = parts[qt + 1:]
        if len(sub) == 1:
            return path.name in {"__init__.py", "py.typed"} or path.stem in QT_MODULES or (path.name.startswith("sip.") and path.suffix == ".pyd")
        if sub[:2] == ("Qt5", "bin"):
            return path.name in QT_DLLS
        if sub[:2] == ("Qt5", "plugins"):
            if sub[2] == "platforms":
                return path.name in {"qwindows.dll", "qoffscreen.dll", "qminimal.dll"}
            return sub[2] in {"iconengines", "imageformats", "styles"}
        return False
    if any(part.endswith(".dist-info") for part in parts):
        return path.name in {"METADATA", "WHEEL", "top_level.txt", "entry_points.txt"} or any(
            token in path.name.lower() for token in ("license", "copying", "copyright", "notice")) or "licenses" in parts
    return True


def main():
    release = ROOT / "release"
    build = ROOT / ".verification" / "single-file-build"
    build.mkdir(parents=True, exist_ok=True)
    release.mkdir(exist_ok=True)
    files = [ROOT / name for name in ROOT_FILES]
    files.extend(file for file in (ROOT / "licenses").iterdir() if file.is_file())
    files.extend((ROOT / "assets" / "fonts").glob("*.ttf"))
    for directory in (ROOT / "core" / "runtime", ROOT / "core" / "site-packages"):
        files.extend(path for path in directory.rglob("*") if path.is_file() and runtime_file(path))
    # Font assets must carry their redistributable license.
    if not (ROOT / "licenses" / "SourceHanSerif-OFL-1.1.txt").is_file():
        raise RuntimeError("The bundled Source Han Serif font license is missing")
    files = sorted(set(files))
    from prepare_vc_runtime import main as prepare_vc_runtime
    prepare_vc_runtime()
    files.append(ROOT / "licenses" / "Microsoft-VC-Runtime.rtf")
    mapped = {file.relative_to(ROOT).as_posix(): file for file in files}
    for file in (ROOT / "core" / "redist").glob("*.dll"):
        mapped["core/runtime/" + file.name] = file
    mapped["core/runtime/VC-RUNTIME-ORIGIN.json"] = ROOT / "core" / "redist" / "ORIGIN.json"
    secrets = private_values()
    manifest = []
    payload = build / "payload.zip"
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for relative, file in sorted(mapped.items()):
            data = file.read_bytes()
            if any(value in data for value in secrets):
                raise RuntimeError(f"Build refused: a configured credential matched {file.relative_to(ROOT)}")
            if relative.startswith(("config/local_",)) and relative != "config/local_models.example.json":
                raise RuntimeError("A private configuration entered the file list")
            manifest.append({"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            info = zipfile.ZipInfo(relative, date_time=(2026, 10, 20, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compresslevel=6)
        info = zipfile.ZipInfo("PACKAGE_MANIFEST.json", date_time=(2026, 10, 20, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, json.dumps({"project": "PaperRoute", "version": "0.1.0", "files": manifest}, indent=2), compresslevel=6)
    with zipfile.ZipFile(payload) as archive:
        assert archive.testzip() is None, "The payload ZIP is corrupt"
        names = archive.namelist()
        assert "core/site-packages/PyQt5/Qt5/bin/Qt5Widgets.dll" in names
        assert any(name.startswith("core/site-packages/PyQt5/sip.") and name.endswith(".pyd") for name in names)
        assert not any("zotero" in name.lower() or "local_models.json" in name or "local_gui_config.json" in name for name in names)
    # A fresh expansion catches pruning mistakes before a GUI exe is produced.
    with tempfile.TemporaryDirectory(prefix="probe-", dir=build) as temporary:
        check = Path(temporary)
        with zipfile.ZipFile(payload) as archive:
            archive.extractall(check)
        environment = dict(os.environ, PAPERROUTE_DATA_DIR=str(check / "userdata"), PAPERROUTE_NO_LEGACY_IMPORT="1",
                           PDF2ZH_CACHE_DIR=str(check / "userdata/cache"), QT_QPA_PLATFORM="offscreen",
                           QT_PLUGIN_PATH=str(check / "core/site-packages/PyQt5/Qt5/plugins"))
        probe = '''import pathlib, sys
import onnxruntime, numpy, cv2, fitz, pikepdf
from PyQt5 import QtCore, QtGui, QtWidgets, QtNetwork, QtSvg, sip
from pdf2zh.doclayout import DocLayoutModel
from pdf2zh.gui_pyqt5 import PDF2ZHMainWindow
from pdf2zh.high_level import download_remote_fonts
from rapidocr_onnxruntime import RapidOCR
app=QtWidgets.QApplication([])
window=PDF2ZHMainWindow()
assert window.threads_spin.maximum()==256
model=DocLayoutModel.load_available()
assert model.model is not None
assert pathlib.Path(download_remote_fonts('zh')).is_relative_to(pathlib.Path(sys.executable).parents[2])
window.close()
print('Clean packaged runtime: Qt, sip, ONNX layout, PDF, OCR imports and bundled Chinese font passed', flush=True)
'''
        subprocess.run([str(check / "core/runtime/python.exe"), "-c", probe], cwd=check, env=environment, check=True, timeout=90)
    payload_id = hashlib.sha256(payload.read_bytes()).hexdigest()[:24]
    identity = build / "PayloadIdentity.cs"
    identity.write_text('internal static partial class PaperRouteSingleFile { private const string PayloadId = "' + payload_id + '"; }', encoding="utf-8")
    output = release / "PaperRoute.exe"
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    command = [str(compiler), "/nologo", "/target:winexe", "/platform:x64", "/optimize+", "/reference:System.Windows.Forms.dll",
               "/reference:System.Drawing.dll", "/reference:System.IO.Compression.dll", "/reference:System.IO.Compression.FileSystem.dll",
               f'/win32icon:{ROOT / "assets" / "paperroute.ico"}', f"/out:{output}",
               f'/win32manifest:{ROOT / "launcher_src" / "PaperRouteSingleFile.manifest"}',
               f"/resource:{payload},PaperRoute.Payload.zip", str(ROOT / "launcher_src" / "PaperRouteSingleFile.cs"), str(identity)]
    subprocess.run(command, cwd=ROOT, check=True)
    package_bytes = sum(entry["bytes"] for entry in manifest)
    original_bytes = sum(path.stat().st_size for folder in (ROOT / "core/runtime", ROOT / "core/site-packages")
                         for path in folder.rglob("*") if path.is_file()) + (ROOT / "assets/doclayout_yolo.onnx").stat().st_size
    report = {"version": "0.1.0", "payload_id": payload_id, "files": len(manifest), "runtime_bytes": package_bytes,
              "original_core_and_layout_bytes": original_bytes, "exe_bytes": output.stat().st_size,
              "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "credential_scan": "passed",
              "repository": "https://github.com/508liang/PaperRoute", "upstream_shell_license": "unspecified; see LICENSE_SCOPE.md",
              "removed": ["unused Qt modules and QML", "video encoding DLL and face cascades", "dependency tests and headers",
                          "Zotero plugins", "Mac GUI", "promotion assets", "user files, history, keys, logs and backups"]}
    (release / "PaperRoute-package.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
