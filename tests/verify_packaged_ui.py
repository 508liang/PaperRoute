"""Inspect the trimmed runtime's real Windows UI at the current desktop DPI."""

import ctypes
import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(sys.argv[1]).resolve()
DATA = ROOT / ".verification" / ("ui-" + RUNTIME.name)
os.environ["PAPERROUTE_DATA_DIR"] = str(DATA)
os.environ["PAPERROUTE_NO_LEGACY_IMPORT"] = "1"
os.environ["PDF2ZH_CACHE_DIR"] = str(DATA / "cache")
os.environ["QT_PLUGIN_PATH"] = str(RUNTIME / "core/site-packages/PyQt5/Qt5/plugins")
os.environ.pop("QT_QPA_PLATFORM", None)
sys.path.insert(0, str(RUNTIME))
sys.path.insert(0, str(RUNTIME / "core/site-packages"))
config = DATA / "config"
config.mkdir(parents=True, exist_ok=True)
(config / "local_engine_config.json").write_text("{}", encoding="utf-8")
(config / "local_gui_config.json").write_text(json.dumps({"service": "多模型自动切换", "font_size_level": "小", "auto_open": False}), encoding="utf-8")

import _launcher
_launcher.preload_onnxruntime()
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFontInfo
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox
from pdf2zh.gui_pyqt5 import PDF2ZHMainWindow
from pdf2zh.model_pool_dialog import ModelPoolDialog
from pdf2zh.local_config import encode_key, save_pool_settings
from pdf2zh.paperroute_brand import stylesheet


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication([])
    app.setStyle("Fusion")
    dpr = app.primaryScreen().devicePixelRatio()
    app.setStyleSheet(stylesheet(12, 1.0 / max(1.0, dpr ** 0.6)))
    save_pool_settings({"profiles": [{"enabled": True, "name": "Primary", "base_url": "http://127.0.0.1:8000/v1", "model": "test-model",
                                     "api_key": encode_key("demo-key-only")}]})
    window = PDF2ZHMainWindow()
    _launcher.ensure_window_visible(window, app)
    from pdf2zh.window_activation import show_main_window
    show_main_window(window)
    dialog = ModelPoolDialog(window)
    dialog.add_aliyun()
    assert dialog.table.item(1, 3).text() == "qwen-plus"
    dialog.table.cellWidget(0, 4).setText("changed-demo-key")
    QDialog.move(dialog, window.geometry().center() - dialog.rect().center())
    dialog.show()

    def inspect():
        try:
            user = ctypes.windll.user32
            assert user.IsWindowVisible(int(dialog.winId()))
            button = dialog.save_button
            assert button.isVisibleTo(dialog)
            assert dialog.rect().contains(button.mapTo(dialog, button.rect().bottomRight()))
            assert app.primaryScreen().availableGeometry().contains(dialog.frameGeometry())
            assert window._left_panel.width() <= 286
            assert dialog.has_unsaved_changes()
            sys.path.insert(0, str(ROOT / "tests"))
            from verify_exe_activation import capture_window
            capture_window(user, int(window.winId()), ROOT / ".verification" / "packaged-main-desktop.png")
            capture_window(user, int(dialog.winId()), ROOT / ".verification" / "packaged-models-desktop.png")

            def dismiss_confirmation():
                question = app.activeModalWidget()
                assert isinstance(question, QMessageBox)
                capture_window(user, int(question.winId()), ROOT / ".verification" / "unsaved-models-desktop.png")
                question.button(QMessageBox.Cancel).click()

            QTimer.singleShot(200, dismiss_confirmation)
            dialog.reject()
            assert dialog.isVisible(), "Continue editing unexpectedly closed the model editor"
            button.click()
            assert dialog.result() == QDialog.Accepted
            report = {"dpi_ratio": dpr, "sidebar_width": window._left_panel.width(),
                      "body_font": QFontInfo(window.service_combo.font()).family(),
                      "quote_font": QFontInfo(window.greeting_label.font()).family(), "save_button_visible": True,
                      "save_button_height": button.height(), "save_button_inside_dialog": True,
                      "unsaved_close_confirmation": "passed", "native_windows": "passed", "runtime": str(RUNTIME)}
            (ROOT / ".verification" / "packaged-ui-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False), flush=True)
            window.close()
            app.quit()
        except Exception:
            traceback.print_exc()
            app.exit(1)

    QTimer.singleShot(900, inspect)
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
