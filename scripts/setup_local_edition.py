"""One-time local migration. Never print or modify the original credentials."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core" / "site-packages"))

from pdf2zh.local_config import (
    POOL_PATH, atomic_write_json, decode_key, load_pool_settings,
    portable_config_path, save_pool_settings,
)
from pdf2zh.model_pool_dialog import profile_from_envs


def main():
    gui_path = portable_config_path("local_gui_config.json", Path.home() / "pdf2zh_gui_config.json")
    engine_path = portable_config_path("local_engine_config.json", Path.home() / ".config" / "PDFMathTranslate" / "config.json")
    gui = json.loads(gui_path.read_text(encoding="utf-8")) if gui_path.exists() else {}
    engine = json.loads(engine_path.read_text(encoding="utf-8")) if engine_path.exists() else {}
    service = gui.get("service", "")
    names = {"OpenAI 兼容格式": "openailiked", "OpenAI": "openai", "DeepSeek": "deepseek", "Silicon": "silicon"}
    envs = {}
    for translator in engine.get("translators", []):
        if translator.get("name") == names.get(service):
            envs.update(translator.get("envs", {}))
    envs.update({key: decode_key(value) for key, value in gui.get("api_configs", {}).items()})
    settings = load_pool_settings()
    if not POOL_PATH.exists():
        profile = profile_from_envs(service, envs)
        if profile:
            settings["profiles"] = [profile]
        save_pool_settings(settings)
    if any(p.get("enabled", True) for p in settings["profiles"]):
        gui["service"] = "多模型自动切换"
    gui.setdefault("threads", 16)
    atomic_write_json(gui_path, gui)
    print("Local configuration ready; original files preserved.")
    print(f"Model profiles: {len(settings['profiles'])}; request timeout: {settings['request_timeout']} s; QPS: {settings['qps']}")


if __name__ == "__main__":
    main()
