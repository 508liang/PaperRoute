"""Regression checks using a local HTTP server; no paid API calls."""

import concurrent.futures
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import uuid
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = Path(os.environ.get("PAPERROUTE_TEST_RUNTIME") or ROOT)
sys.path.insert(0, str(RUNTIME_ROOT / "core" / "site-packages"))
os.environ["PDF2ZH_CACHE_DIR"] = str(ROOT / ".verification" / "cache")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_PLUGIN_PATH"] = str(RUNTIME_ROOT / "core" / "site-packages" / "PyQt5" / "Qt5" / "plugins")

from pdf2zh.failover import FailoverTranslator, ModelPool, ModelPoolExhausted, TranslationCancelled
from pdf2zh.local_config import decode_key, encode_key, load_pool_settings, save_pool_settings


class FakeAPI(BaseHTTPRequestHandler):
    records = []
    lock = threading.Lock()

    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        model = payload["model"]
        with self.lock:
            self.records.append((model, time.monotonic(), self.headers.get("Authorization"), payload))
        try:
            if model == "hang":
                time.sleep(2)
            if model == "trickle":
                self.send_response(200)
                self.send_header("Content-Length", "10000")
                self.end_headers()
                for _ in range(50):
                    self.wfile.write(b" ")
                    self.wfile.flush()
                    time.sleep(0.04)
                return
            if model in ("limited", "unauthorized", "offline"):
                self.send_response({"limited": 429, "unauthorized": 401, "offline": 503}[model])
                self.send_header("Retry-After", "2")
                self.end_headers()
                return
            if model == "broken":
                body = b"not JSON"
            else:
                content = "" if model == "empty" else "<think>reasoning only</think>" if model == "thinking" else "这是验证自动切换和继续翻译的测试译文。"
                body = json.dumps({"choices": [{"message": {"content": content}}]}, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


class FailoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeAPI)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        with FakeAPI.lock:
            FakeAPI.records.clear()

    def settings(self, *models, timeout=0.3, qps=0):
        return {"request_timeout": timeout, "cooldown": 2, "qps": qps,
                "profiles": [{"enabled": True, "name": f"Candidate {i}", "base_url": self.url,
                              "model": model, "api_key": encode_key(f"test-key-{i}")}
                             for i, model in enumerate(models)]}

    def translate(self, pool):
        return pool.translate([{"role": "user", "content": "Test paragraph"}])

    def test_timeout_rate_limit_empty_and_invalid_reply_then_continue(self):
        status = []
        pool = ModelPool(self.settings("hang", "limited", "empty", "thinking", "broken", "good"), on_status=status.append)
        start = time.monotonic()
        self.assertIn("测试译文", self.translate(pool))
        self.assertLess(time.monotonic() - start, 1.8)
        self.assertEqual([r[0] for r in FakeAPI.records], ["hang", "limited", "empty", "thinking", "broken", "good"])
        self.assertEqual(len(status), 5)
        self.translate(pool)
        self.assertEqual([r[0] for r in FakeAPI.records][-2:], ["good", "good"])

    def test_trickling_reply_obeys_total_deadline(self):
        pool = ModelPool(self.settings("trickle", "good", timeout=0.25))
        start = time.monotonic()
        self.assertIn("测试译文", self.translate(pool))
        self.assertLess(time.monotonic() - start, 1.2)

    def test_all_models_fail_once_without_unbounded_retry(self):
        pool = ModelPool(self.settings("unauthorized", "offline", timeout=2))
        with self.assertRaises(ModelPoolExhausted) as captured:
            self.translate(pool)
        self.assertEqual(len(FakeAPI.records), 2)
        self.assertNotIn("test-key", str(captured.exception))
        with self.assertRaises(ModelPoolExhausted):
            self.translate(pool)
        self.assertEqual(len(FakeAPI.records), 2)

    def test_cancellation_aborts_waiting_http_request(self):
        cancelled = threading.Event()
        pool = ModelPool(self.settings("hang", "good", timeout=5), cancel_event=cancelled)
        timer = threading.Timer(0.15, cancelled.set)
        timer.start()
        start = time.monotonic()
        try:
            with self.assertRaises(TranslationCancelled):
                self.translate(pool)
        finally:
            timer.cancel()
        self.assertLess(time.monotonic() - start, 1)
        self.assertEqual([r[0] for r in FakeAPI.records], ["hang"])

    def test_concurrent_paragraphs_share_cooldown_and_do_not_lose_work(self):
        pool = ModelPool(self.settings("offline", "good", timeout=2))
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda i: self.translate(pool), range(24)))
        self.assertEqual(len(results), 24)
        self.assertTrue(all("测试译文" in result for result in results))
        counts = Counter(r[0] for r in FakeAPI.records)
        self.assertEqual(counts["good"], 24)
        self.assertLessEqual(counts["offline"], 8)

    def test_qps_is_separate_from_thread_count(self):
        pool = ModelPool(self.settings("good", qps=8, timeout=2))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda i: self.translate(pool), range(4)))
        starts = sorted(r[1] for r in FakeAPI.records)
        self.assertGreaterEqual(starts[-1] - starts[0], 0.30)

    def test_independent_credentials_and_thinking_option(self):
        settings = self.settings("unauthorized", "good")
        settings["profiles"][1]["disable_thinking"] = True
        self.translate(ModelPool(settings))
        self.assertEqual([r[2] for r in FakeAPI.records], ["Bearer test-key-0", "Bearer test-key-1"])
        self.assertIs(FakeAPI.records[-1][3]["enable_thinking"], False)

    def test_completed_paragraphs_use_cache_when_retrying(self):
        pool = ModelPool(self.settings("good"))
        text = "cache-check-" + str(uuid.uuid4())
        first = FailoverTranslator("en", "zh", envs={"_LOCAL_MODEL_POOL": pool})
        result = first.translate(text)
        second = FailoverTranslator("en", "zh", envs={"_LOCAL_MODEL_POOL": ModelPool(self.settings("good"))})
        self.assertEqual(second.translate(text), result)
        self.assertEqual(len(FakeAPI.records), 1)

    def test_invalid_config_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".verification") as folder:
            path = Path(folder) / "models.json"
            path.write_text("broken", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_pool_settings(path)
            self.assertEqual(path.read_text(), "broken")
            settings = self.settings("good")
            save_pool_settings(settings, path)
            self.assertEqual(decode_key(load_pool_settings(path)["profiles"][0]["api_key"]), "test-key-0")

    def test_table_and_figure_failures_do_not_report_success(self):
        from pdf2zh.high_level import _postprocess_figures, _postprocess_tables

        source, target = MagicMock(), MagicMock()
        source.page_count = target.page_count = 1
        translator = MagicMock()
        translator.manages_retries = True
        translator.translate.side_effect = ModelPoolExhausted("All candidates failed")
        page = source.__getitem__.return_value
        page.find_tables.return_value = SimpleNamespace(tables=[SimpleNamespace(cells=[(10, 10, 100, 50)])])
        page.get_text.return_value = "Scientific table description"
        with self.assertRaises(ModelPoolExhausted):
            _postprocess_tables(target, translator, doc_original=source)
        page.get_text.return_value = {"blocks": [{"type": 0, "lines": [{"spans": [
            {"text": "Scientific figure description", "bbox": (10, 10, 100, 50), "size": 12}]}]}]}
        target.__getitem__.return_value.get_text.return_value = ""
        with self.assertRaises(ModelPoolExhausted):
            _postprocess_figures(target, translator, doc_original=source)


class GUIEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import onnxruntime  # Same preload order as the actual launcher.
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        from PyQt5.QtGui import QFont, QFontDatabase
        for filename in ("msyh.ttc", "segoeui.ttf"):
            font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename
            if font_path.exists():
                QFontDatabase.addApplicationFont(str(font_path))
        cls.app.setFont(QFont("Microsoft YaHei", 10))
        from pdf2zh.paperroute_brand import stylesheet
        cls.app.setStyleSheet(stylesheet(12, 1))

    def test_editor_save_reload_order_masking_and_main_window(self):
        from PyQt5.QtWidgets import QCheckBox, QDialog, QLineEdit
        from pdf2zh import local_config
        from pdf2zh.gui_pyqt5 import HAS_ZOTERO, PDF2ZHMainWindow, UserConfigManager
        from pdf2zh.model_pool_dialog import ModelPoolDialog
        with tempfile.TemporaryDirectory(dir=ROOT / ".verification") as folder:
            folder = Path(folder)
            (folder / "local_engine_config.json").write_text("{}", encoding="utf-8")
            (folder / "local_gui_config.json").write_text(json.dumps({"service": "多模型自动切换", "threads": 64,
                                                                       "api_configs": {"TEST_API_KEY": encode_key("existing-key")},
                                                                       "user_prompt_templates": {"test": "keep me"}}), encoding="utf-8")
            profile = {"enabled": True, "name": "Primary", "base_url": "http://127.0.0.1:8000/v1",
                       "model": "first", "api_key": encode_key("masked-test-key")}
            with patch.object(local_config, "POOL_PATH", folder / "local_models.json"), patch.object(local_config, "CONFIG_DIR", folder):
                dialog = ModelPoolDialog(current_profile=profile)
                self.assertEqual(dialog.table.cellWidget(0, 4).echoMode(), QLineEdit.Password)
                dialog.duplicate()
                dialog.table.item(1, 1).setText("Backup")
                dialog.table.item(1, 3).setText("second")
                dialog.move(-1)
                dialog.accept()
                self.assertEqual(dialog.result(), QDialog.Accepted)
                reopened = ModelPoolDialog()
                self.assertEqual(reopened.table.item(0, 1).text(), "Backup")
                self.assertEqual(reopened.table.rowCount(), 2)
                self.assertEqual(reopened.table.cellWidget(0, 4).text(), "masked-test-key")
                window = PDF2ZHMainWindow()
                window.show()
                self.app.processEvents()
                self.assertFalse(HAS_ZOTERO)
                self.assertEqual(window.threads_spin.maximum(), 256)
                self.assertEqual(window.threads_spin.value(), 64)
                self.assertTrue(window.model_pool_btn.isVisible())
                self.assertFalse(window.advanced_panel.isVisible())
                self.assertTrue(window.threads_spin.isVisible())
                from pdf2zh.paperroute_brand import QUOTE
                self.assertEqual(window.greeting_label.text(), QUOTE)
                self.assertLessEqual(window._left_panel.width(), 286)
                window.advanced_toggle.click()
                self.app.processEvents()
                self.assertTrue(window.advanced_panel.isVisible())
                self.assertTrue(window.ignore_cache_check.isEnabled())
                window.skip_fonts_check.setChecked(True)
                window.advanced_toggle.click()
                self.app.processEvents()
                self.assertFalse(window.advanced_panel.isVisible())
                self.assertTrue(window.skip_fonts_check.isChecked())
                window.save_current_config()
                saved = UserConfigManager.load_config()
                self.assertIn("TEST_API_KEY", saved["api_configs"])
                self.assertIn("test", saved["user_prompt_templates"])
                self.assertFalse(any("Zotero" in c.text() for c in window.findChildren(QCheckBox)))
                output = ROOT / ".verification"
                window.grab().save(str(output / "main-window.png"))
                window.advanced_toggle.click()
                self.app.processEvents()
                window.grab().save(str(output / "paperroute-expanded.png"))
                window.advanced_toggle.click()
                reopened.show()
                self.app.processEvents()
                reopened.grab().save(str(output / "model-pool.png"))
                reopened.reject()
                window.close()

    def test_aliyun_preset_saves_without_calling_the_service(self):
        from pdf2zh import local_config
        from pdf2zh.model_pool_dialog import ModelPoolDialog
        with tempfile.TemporaryDirectory(dir=ROOT / ".verification") as folder:
            path = Path(folder) / "local_models.json"
            with patch.object(local_config, "POOL_PATH", path):
                dialog = ModelPoolDialog()
                dialog.add_aliyun()
                self.assertEqual(dialog.table.item(0, 2).text(), "https://dashscope.aliyuncs.com/compatible-mode/v1")
                self.assertEqual(dialog.table.item(0, 3).text(), "qwen-plus")
                self.assertTrue(dialog.table.cellWidget(0, 5).isChecked())
                self.assertTrue(dialog.has_unsaved_changes())
                self.assertFalse(path.exists())
                dialog.table.cellWidget(0, 4).setText("aliyun-key-for-test")
                dialog.accept()
                saved = load_pool_settings()
                self.assertEqual(decode_key(saved["profiles"][0]["api_key"]), "aliyun-key-for-test")

    def test_unsaved_model_edits_confirm_on_close_and_escape(self):
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        from PyQt5.QtWidgets import QDialog, QMessageBox
        from pdf2zh import local_config
        from pdf2zh.model_pool_dialog import ModelPoolDialog
        with tempfile.TemporaryDirectory(dir=ROOT / ".verification") as folder:
            pool_path = Path(folder) / "local_models.json"
            with patch.object(local_config, "POOL_PATH", pool_path):
                dialog = ModelPoolDialog(current_profile={"name": "test", "base_url": "http://127.0.0.1/v1", "model": "first"})
                dialog.show()
                self.app.processEvents()
                self.assertTrue(dialog.has_unsaved_changes())
                self.assertTrue(dialog.save_button.isVisible())
                self.assertTrue(dialog.rect().contains(dialog.save_button.mapTo(dialog, dialog.save_button.rect().bottomRight())))
                with patch.object(QMessageBox, "exec_", return_value=QMessageBox.Cancel):
                    dialog.close()
                self.assertTrue(dialog.isVisible())
                self.assertFalse(pool_path.exists())
                with patch.object(QMessageBox, "exec_", return_value=QMessageBox.Save):
                    QTest.keyClick(dialog, Qt.Key_Escape)
                self.assertFalse(dialog.isVisible())
                self.assertEqual(dialog.result(), QDialog.Accepted)
                before = pool_path.read_bytes()
                reopened = ModelPoolDialog()
                self.assertFalse(reopened.has_unsaved_changes())
                reopened.show()
                reopened.table.cellWidget(0, 4).setText("temporary-unsaved-key")
                self.assertTrue(reopened.has_unsaved_changes())
                with patch.object(QMessageBox, "exec_", return_value=QMessageBox.Discard):
                    reopened.close()
                self.assertFalse(reopened.isVisible())
                self.assertEqual(pool_path.read_bytes(), before)

                invalid = ModelPoolDialog()
                invalid.show()
                invalid.table.item(0, 2).setText("invalid-url")
                with patch.object(QMessageBox, "exec_", return_value=QMessageBox.Save), patch.object(QMessageBox, "warning"):
                    invalid.reject()
                self.assertTrue(invalid.isVisible())
                self.assertEqual(pool_path.read_bytes(), before)
                with patch.object(QMessageBox, "exec_", return_value=QMessageBox.Discard):
                    invalid.reject()


if __name__ == "__main__":
    unittest.main(verbosity=2)
