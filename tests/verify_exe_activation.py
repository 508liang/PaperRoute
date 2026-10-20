"""Verify native Windows visibility by launching the actual pdf2zh.exe."""

import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core" / "site-packages"))
from pdf2zh.window_activation import _windows_api


def main():
    # Native capture coordinates must use physical pixels on a scaled desktop.
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    user, kernel = _windows_api()
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user.GetForegroundWindow.restype = wintypes.HWND
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    expected_runtime = os.path.normcase(str(ROOT / "core" / "runtime" / "pythonw.exe"))

    def windows():
        records = []

        @callback_type
        def visit(handle, unused):
            length = user.GetWindowTextLengthW(handle)
            if not length:
                return True
            title = ctypes.create_unicode_buffer(length + 1)
            user.GetWindowTextW(handle, title, len(title))
            if "PaperRoute" not in title.value:
                return True
            process_id = wintypes.DWORD()
            user.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
            process = kernel.OpenProcess(0x1000, False, process_id.value)
            if not process:
                return True
            try:
                image = ctypes.create_unicode_buffer(32768)
                size = wintypes.DWORD(len(image))
                if kernel.QueryFullProcessImageNameW(process, 0, image, ctypes.byref(size)):
                    if os.path.normcase(image.value) == expected_runtime:
                        records.append({"pid": process_id.value, "handle": handle, "title": title.value,
                                        "visible": bool(user.IsWindowVisible(handle)), "minimized": bool(user.IsIconic(handle))})
            finally:
                kernel.CloseHandle(process)
            return True

        user.EnumWindows(visit, 0)
        return records

    def launch_and_check(case, entry="PaperRoute.exe"):
        started = time.monotonic()
        process = subprocess.Popen([str(ROOT / entry)], cwd=str(ROOT))
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            raise AssertionError("The executable stub did not exit after dispatching the launcher")
        assert process.returncode == 0, process.returncode
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            current = windows()
            if len(current) == 1 and current[0]["visible"] and not current[0]["minimized"]:
                record = dict(current[0], case=case, seconds=round(time.monotonic() - started, 2),
                              foreground=user.GetForegroundWindow() == current[0]["handle"])
                print(json.dumps(record, ensure_ascii=False), flush=True)
                return record
            time.sleep(0.1)
        raise AssertionError(f"The actual executable did not restore a visible window: {current}")

    before = windows()
    results = [launch_and_check("current-window")]
    handle = results[0]["handle"]
    # Let the initial Qt/native show requests settle before changing window state.
    time.sleep(0.8)
    try:
        user.ShowWindow(handle, 6)
        deadline = time.monotonic() + 3
        while not user.IsIconic(handle) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert user.IsIconic(handle), "Could not minimize the test window"
        results.append(launch_and_check("minimized-window"))
        user.ShowWindow(handle, 0)
        assert not user.IsWindowVisible(handle), "Could not hide the test window"
        results.append(launch_and_check("hidden-window"))
        results.append(launch_and_check("legacy-pdf2zh-entry", "pdf2zh.exe"))
    finally:
        user.ShowWindow(handle, 9 if user.IsIconic(handle) else 5)
        user.SetForegroundWindow(handle)
    assert len({item["pid"] for item in results}) == 1, "Repeated launches created duplicate GUI instances"
    report = {"before": before, "results": results, "duplicate_instances": False}
    out = ROOT / ".verification"
    out.mkdir(exist_ok=True)
    (out / "exe-activation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    capture_window(user, handle, out / "paperroute-desktop.png")


def capture_window(user, handle, destination):
    """Capture just the actual application window, including its native frame."""
    from PIL import Image

    user.IsIconic.argtypes = [wintypes.HWND]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    if user.IsIconic(handle) or not user.IsWindowVisible(handle):
        print("Native screenshot skipped because the application was minimized or hidden", flush=True)
        return False

    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.GetWindowDC.argtypes = [wintypes.HWND]
    user.GetWindowDC.restype = wintypes.HDC
    user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user.PrintWindow.restype = wintypes.BOOL
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi.SelectObject.restype = wintypes.HANDLE
    gdi.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    gdi.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]

    class Header(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("width", wintypes.LONG), ("height", wintypes.LONG),
                    ("planes", wintypes.WORD), ("bits", wintypes.WORD), ("compression", wintypes.DWORD),
                    ("image_size", wintypes.DWORD), ("x_ppm", wintypes.LONG), ("y_ppm", wintypes.LONG),
                    ("colors", wintypes.DWORD), ("important", wintypes.DWORD)]

    bounds = wintypes.RECT()
    assert user.GetWindowRect(handle, ctypes.byref(bounds))
    width, height = bounds.right - bounds.left, bounds.bottom - bounds.top
    assert 0 < width < 10000 and 0 < height < 10000
    screen = user.GetWindowDC(handle)
    memory = gdi.CreateCompatibleDC(screen)
    bitmap = gdi.CreateCompatibleBitmap(screen, width, height)
    previous = gdi.SelectObject(memory, bitmap)
    try:
        assert user.PrintWindow(handle, memory, 2), "Native window capture failed"
        gdi.SelectObject(memory, previous)
        previous = None
        info = Header(ctypes.sizeof(Header), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        pixels = (ctypes.c_ubyte * (width * height * 4))()
        assert gdi.GetDIBits(screen, bitmap, 0, height, pixels, ctypes.byref(info), 0) == height
        Image.frombytes("RGB", (width, height), bytes(pixels), "raw", "BGRX").save(destination)
        print("Actual PaperRoute window screenshot captured", flush=True)
    finally:
        if previous:
            gdi.SelectObject(memory, previous)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(memory)
        user.ReleaseDC(handle, screen)


if __name__ == "__main__":
    main()
