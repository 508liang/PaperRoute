"""Launch the real desktop entry point and capture its initial state."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core" / "site-packages"))

import _launcher

_original = _launcher.ensure_window_visible


def checked_window(window, app):
    _original(window, app)
    from PyQt5.QtCore import QTimer
    from pdf2zh.local_config import load_pool_settings

    def capture():
        out = ROOT / ".verification"
        out.mkdir(exist_ok=True)
        window.grab().save(str(out / "live-launch.png"))
        report = {"title": window.windowTitle(), "visible": window.isVisible(),
                  "active_service": window.service_combo.currentText(), "threads": window.threads_spin.value(),
                  "maximum_threads": window.threads_spin.maximum(), "pool_button_visible": window.model_pool_btn.isVisible(),
                  "configured_models": len(load_pool_settings()["profiles"])}
        (out / "live-launch.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    QTimer.singleShot(1000, capture)


_launcher.ensure_window_visible = checked_window
_launcher.main()
