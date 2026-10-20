"""Launch the shipped exe in isolation; verify native visibility and cache reuse."""

import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "core" / "site-packages"))
from pdf2zh.window_activation import _windows_api
from verify_exe_activation import capture_window


def main():
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    package = json.loads((ROOT / "release" / "PaperRoute-package.json").read_text(encoding="utf-8"))
    data = ROOT / ".verification" / ("single-file-" + package["payload_id"])
    data.mkdir(parents=True, exist_ok=True)
    config = data / "config"
    config.mkdir(exist_ok=True)
    # Dummy values only. Do not import or modify the user's real model profiles.
    for name, value in (("local_engine_config.json", {}), ("local_gui_config.json", {"font_size_level": "小", "auto_open": False,
                         "service": "多模型自动切换"}), ("local_models.json", {"profiles": []})):
        (config / name).write_text(json.dumps(value), encoding="utf-8")
    runtime = data / "runtime" / package["payload_id"]
    cold = not (runtime / ".ready").exists()
    env = dict(os.environ, PAPERROUTE_DATA_DIR=str(data), PAPERROUTE_NO_MIGRATION="1")
    env.pop("QT_QPA_PLATFORM", None)
    user, kernel = _windows_api()
    user.GetForegroundWindow.restype = wintypes.HWND
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    expected = os.path.normcase(str(runtime / "core" / "runtime" / "pythonw.exe"))

    def windows():
        records = []

        @callback_type
        def visit(handle, unused):
            title = ctypes.create_unicode_buffer(512)
            user.GetWindowTextW(handle, title, len(title))
            if "PaperRoute" not in title.value and "pdf2zh -" not in title.value:
                return True
            process_id = wintypes.DWORD()
            user.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
            process = kernel.OpenProcess(0x1000, False, process_id.value)
            if process:
                try:
                    image = ctypes.create_unicode_buffer(32768)
                    size = wintypes.DWORD(len(image))
                    if kernel.QueryFullProcessImageNameW(process, 0, image, ctypes.byref(size)) and os.path.normcase(image.value) == expected:
                        records.append({"handle": handle, "pid": process_id.value, "visible": bool(user.IsWindowVisible(handle)),
                                        "minimized": bool(user.IsIconic(handle)), "title": title.value})
                finally:
                    kernel.CloseHandle(process)
            return True

        user.EnumWindows(visit, 0)
        return records

    def launch():
        start = time.monotonic()
        child = subprocess.Popen([str(ROOT / "release" / "PaperRoute.exe")], cwd=data, env=env)
        try:
            child.wait(timeout=100)
        except subprocess.TimeoutExpired:
            child.terminate()
            child.wait(timeout=5)
            raise AssertionError("The single-file launcher did not finish dispatching")
        assert child.returncode == 0, child.returncode
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            records = windows()
            if any("启动失败" in record["title"] or "运行错误" in record["title"] for record in records):
                raise AssertionError("The packaged GUI reported a startup error; inspect the isolated startup log")
            if len(records) == 1 and records[0]["visible"] and not records[0]["minimized"]:
                return dict(records[0], seconds=round(time.monotonic() - start, 2))
            time.sleep(0.1)
        raise AssertionError(f"Packaged exe did not display a native window: {records}")

    results = []
    try:
        results.append(launch())
        manifest = json.loads((runtime / "PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
        assert len(manifest["files"]) == package["files"]
        assert not any(p.name.startswith("zotero") for p in runtime.rglob("*.py"))
        time.sleep(0.8)
        capture_window(user, results[0]["handle"], ROOT / ".verification" / "single-file-desktop.png")
        ready_mtime = (runtime / ".ready").stat().st_mtime_ns
        results.append(launch())
        assert results[0]["pid"] == results[1]["pid"], "Warm launch created a duplicate GUI"
        assert ready_mtime == (runtime / ".ready").stat().st_mtime_ns, "Warm launch unnecessarily extracted the runtime"
        report = {"cold_extraction": cold, "exe_bytes": package["exe_bytes"], "results": results,
                  "runtime": str(runtime), "data": str(data), "cache_reused": True, "native_window": "passed"}
        (ROOT / ".verification" / "single-file-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False), flush=True)
    finally:
        # Close only the window belonging to this test's isolated extracted exe.
        time.sleep(0.5)  # Let the last activation helper finish before closing.
        for record in windows():
            user.PostMessageW(record["handle"], 0x0010, 0, 0)
        deadline = time.monotonic() + 4
        while windows() and time.monotonic() < deadline:
            time.sleep(0.1)
    subprocess.run([str(runtime / "core/runtime/python.exe"), str(ROOT / "tests/verify_packaged_ui.py"), str(runtime)],
                   cwd=ROOT, env=env, check=True, timeout=35)
    pipeline_env = dict(env, PAPERROUTE_TEST_RUNTIME=str(runtime), PAPERROUTE_NO_LEGACY_IMPORT="1",
                        PDF2ZH_CACHE_DIR=str(data / "pipeline-cache"))
    subprocess.run([str(runtime / "core/runtime/python.exe"), str(ROOT / "tests/verify_pdf_pipeline.py")],
                   cwd=ROOT, env=pipeline_env, check=True, timeout=90)
    # Release only caches produced by this verifier, including failed earlier
    # iterations. The complete install, release exe and personal files stay out.
    verification = (ROOT / ".verification").resolve()
    handles = []

    @callback_type
    def find_test_windows(handle, unused):
        process_id = wintypes.DWORD()
        user.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
        process = kernel.OpenProcess(0x1000, False, process_id.value)
        if process:
            try:
                image = ctypes.create_unicode_buffer(32768)
                size = wintypes.DWORD(len(image))
                if kernel.QueryFullProcessImageNameW(process, 0, image, ctypes.byref(size)):
                    path = Path(image.value)
                    try:
                        relative = path.relative_to(verification)
                        if relative.parts[0].startswith("single-file-"):
                            handles.append(handle)
                    except ValueError:
                        pass
            finally:
                kernel.CloseHandle(process)
        return True

    user.EnumWindows(find_test_windows, 0)
    for handle in handles:
        user.PostMessageW(handle, 0x0010, 0, 0)
    time.sleep(0.7)
    removed = 0
    for candidate in [*verification.glob("single-file-*"), verification / "vcredist"]:
        target = candidate.resolve()
        assert target.parent == verification, "Refusing cleanup outside the verification workspace"
        if not target.is_dir():
            continue
        removed += sum(file.stat().st_size for file in target.rglob("*") if file.is_file())
        try:
            shutil.rmtree(target)
        except OSError:
            print("A locked verification cache was retained: " + target.name, flush=True)
    print(f"Temporary extraction/build files cleaned (up to {removed / 1024**2:.0f} MiB)", flush=True)


if __name__ == "__main__":
    main()
