"""Exercise the real Windows worker, layout model, cache, and PDF outputs."""

import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = Path(os.environ.get("PAPERROUTE_TEST_RUNTIME") or ROOT)
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(RUNTIME_ROOT / "core" / "site-packages"))
os.environ["PDF2ZH_CACHE_DIR"] = str(ROOT / ".verification" / "pdf-cache")

import onnxruntime  # Must precede importing Qt.
import fitz
from PyQt5.QtWidgets import QApplication

from test_local_edition import FailoverTests, FakeAPI
from pdf2zh.config import ConfigManager
from pdf2zh.failover import FailoverTranslator
from pdf2zh.gui_pyqt5 import TranslateWorker, BatchTranslateWorker


def main():
    app = QApplication.instance() or QApplication([])
    out = ROOT / ".verification" / "pdf"
    out.mkdir(parents=True, exist_ok=True)
    source = out / "sample.pdf"
    with fitz.open() as document:
        for i in range(2):
            page = document.new_page(width=595, height=842)
            page.insert_text((64, 80), f"Translation continuity check - page {i + 1}", fontsize=18)
            page.insert_textbox(fitz.Rect(64, 125, 530, 235),
                                "A translation request may fail when a model is unavailable. "
                                "The application should retry this paragraph with a backup model. "
                                "Completed paragraphs remain cached for the next attempt.", fontsize=12)
            page.insert_textbox(fitz.Rect(64, 270, 530, 380),
                                "A second paragraph verifies that parallel requests share model health. "
                                "This is a synthetic document with no private research content.", fontsize=12)
        document.save(source)
    # Prefer the bundled output font so the clean single-file edition is checked.
    font = RUNTIME_ROOT / "assets" / "fonts" / "SourceHanSerifCN-Regular.ttf"
    if not font.is_file():
        font = Path.home() / ".cache" / "babeldoc" / "fonts" / "SourceHanSerifCN-Regular.ttf"
    assert font.is_file(), "A cached Chinese font is required for this local-only check"
    ConfigManager.get_instance()._config_data["NOTO_FONT_PATH"] = str(font)
    FailoverTests.setUpClass()
    fixture = FailoverTests()
    settings = fixture.settings("offline", "good", timeout=3)
    original_cwd = Path.cwd()
    os.chdir(out)
    try:
        params = {"translator": FailoverTranslator, "file_path": str(source), "lang_from": "en", "lang_to": "zh",
                  "pages": None, "threads": 8, "local_models": settings, "output_mode": "side_by_side"}
        results, errors, status = [], [], []
        worker = TranslateWorker(params)
        worker.translation_finished.connect(lambda *paths: results.append(paths))
        worker.translation_error.connect(errors.append)
        worker.model_status.connect(status.append)
        start = time.monotonic()
        worker.run()
        app.processEvents()
        elapsed = time.monotonic() - start
        assert not errors, errors
        assert len(results) == 1, "Worker did not finish"
        mono, dual, side = [Path(path).resolve() for path in results[0]]
        with fitz.open(mono) as document:
            assert len(document) == 2
            translated_text = "".join(page.get_text() for page in document)
            assert "测试译文" in translated_text, translated_text
        with fitz.open(dual) as document:
            assert len(document) == 4
        with fitz.open(side) as document:
            assert len(document) == 2
            assert document[0].rect.width == 1190
        assert any("切换" in message for message in status), status
        calls = len(FakeAPI.records)
        # A separate task, as when a user retries, reuses completed paragraph work.
        replay_errors, replay_results = [], []
        replay = TranslateWorker(params)
        replay.translation_error.connect(replay_errors.append)
        replay.translation_finished.connect(lambda *paths: replay_results.append(paths))
        replay.run()
        app.processEvents()
        assert not replay_errors, replay_errors
        assert replay_results
        assert len(FakeAPI.records) == calls, "Retry unnecessarily called the model again"
        report = {"worker": "passed", "mono_pages": 2, "dual_pages": 4, "side_by_side_pages": 2,
                  "failover_observed": True, "api_calls": calls, "api_calls_on_repeat": 0,
                  "first_run_seconds": round(elapsed, 2), "mono": str(mono), "dual": str(dual), "side_by_side": str(side)}
        second = out / "sample-batch.pdf"
        with fitz.open(source) as document:
            document[0].insert_text((64, 450), "A separate PDF verifies the batch queue.", fontsize=12)
            document.save(second)
        batch = BatchTranslateWorker([str(source), str(second)], params)
        batch_files, batch_errors, batch_done, batch_steps = [], [], [], []
        batch.file_finished.connect(lambda *args: batch_files.append(args))
        batch.file_error.connect(lambda *args: batch_errors.append(args))
        batch.batch_finished.connect(lambda *args: batch_done.append(args))
        batch.batch_progress.connect(lambda *args: batch_steps.append(args))
        batch.run()
        app.processEvents()
        assert not batch_errors, batch_errors
        assert batch_done == [(2, 0)], batch_done
        assert [step[0] for step in batch_steps] == [1, 2], batch_steps
        assert batch.translation_envs["_LOCAL_MODEL_POOL"] is not None
        for filename, mono_path, dual_path, side_path in batch_files:
            for path, expected_pages in ((mono_path, 2), (dual_path, 4), (side_path, 2)):
                with fitz.open(path) as document:
                    assert len(document) == expected_pages, (filename, path)
            with fitz.open(mono_path) as document:
                assert "测试译文" in "".join(page.get_text() for page in document), filename
        report["batch"] = {"files": len(batch_files), "success": 2, "failed": 0, "queue_order": [step[0] for step in batch_steps]}
        report["runtime"] = str(RUNTIME_ROOT)
        (out / "pipeline-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
    finally:
        os.chdir(original_cwd)
        FailoverTests.tearDownClass()


if __name__ == "__main__":
    main()
