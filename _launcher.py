"""
pdf2zh 桌面版启动器
由 pdf2zh.vbs 调用，使用 pythonw.exe 运行（无控制台窗口）
错误写入日志文件，并通过 Qt 对话框提示用户
"""
import sys
import os
import traceback
from pathlib import Path
from datetime import datetime

# pythonw.exe 没有控制台，sys.stdout/stderr 为 None，
# 会导致 tqdm 等库写入时崩溃 (AttributeError: 'NoneType' object has no attribute 'write')
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

APP_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get("PAPERROUTE_DATA_DIR") or APP_DIR).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"startup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
_dll_handles = []


def log(msg: str):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")


def show_error_dialog(title: str, message: str):
    """尝试用 Qt 显示错误，失败则用 Windows 原生对话框"""
    try:
        from PyQt5.QtWidgets import QApplication, QMessageBox
        _app = QApplication.instance() or QApplication(sys.argv)
        msg_box = QMessageBox()
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setDetailedText(f"日志文件: {LOG_FILE}")
        msg_box.exec_()
    except Exception:
        # 后备: 使用 Windows MessageBox via ctypes
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                f"{message}\n\n日志文件: {LOG_FILE}",
                title,
                0x10,  # MB_ICONERROR
            )
        except Exception:
            pass


def preload_onnxruntime():
    """在 PyQt5 之前预加载 OnnxRuntime，避免 DLL 搜索路径冲突。

    PyQt5 会修改 Windows DLL 搜索路径，导致 OnnxRuntime 的
    onnxruntime_pybind11_state.pyd 无法找到 VC++ DLL 而加载失败。
    必须在任何 PyQt5 导入之前完成 OnnxRuntime 的加载。
    """
    import threading

    app_dir = str(APP_DIR)

    if hasattr(os, 'add_dll_directory'):
        runtime_dir = os.path.join(app_dir, 'core', 'runtime')
        if os.path.isdir(runtime_dir):
            _dll_handles.append(os.add_dll_directory(os.path.abspath(runtime_dir)))

        onnx_dll_dir = os.path.join(app_dir, 'core', 'site-packages', 'onnxruntime', 'capi')
        if os.path.isdir(onnx_dll_dir):
            _dll_handles.append(os.add_dll_directory(os.path.abspath(onnx_dll_dir)))

    result = [None]
    def _load():
        try:
            import onnxruntime
            import onnx
            result[0] = onnxruntime.__version__
        except Exception as e:
            result[0] = f"ERROR: {e}"

    t = threading.Thread(target=_load, daemon=True)
    t.start()
    t.join(timeout=30)  # 等待加载完成（AI布局检测必须）

    if t.is_alive():
        log("OnnxRuntime 预加载超时（30秒），继续启动")
    elif result[0] and not str(result[0]).startswith("ERROR"):
        log(f"OnnxRuntime 预加载成功: {result[0]}")
    else:
        log(f"OnnxRuntime 预加载失败（AI布局检测将不可用）: {result[0]}")


def ensure_window_visible(window, app):
    """确保窗口在可见屏幕范围内并居中显示（兼容 DPI 缩放）。"""
    screen = app.primaryScreen().availableGeometry()
    # availableGeometry 已经是逻辑像素，直接用
    sw, sh = screen.width(), screen.height()
    w = min(int(sw * 0.85), 1400)
    h = min(int(sh * 0.85), 900)
    # 低分辨率/高缩放时降低最小值
    w = max(w, min(860, sw - 40))
    h = max(h, min(560, sh - 40))
    window.resize(w, h)
    x = screen.x() + (sw - w) // 2
    y = screen.y() + (sh - h) // 2
    window.move(x, y)
    log(f"屏幕逻辑分辨率: {sw}x{sh}, 窗口: {w}x{h}")


def main():
    os.chdir(DATA_DIR)
    log("=== PaperRoute 启动 ===")
    log(f"Python: {sys.version}")
    log(f"工作目录: {os.getcwd()}")

    from pdf2zh.window_activation import activate_existing_window, show_main_window
    if activate_existing_window(APP_DIR):
        log("已唤醒现有窗口，无需重复加载模型")
        return

    # 设置 Qt 插件路径，避免与系统中其他 Qt 安装冲突
    qt_plugin_path = str(APP_DIR / "core" / "site-packages" / "PyQt5" / "Qt5" / "plugins")
    os.environ["QT_PLUGIN_PATH"] = qt_plugin_path
    log(f"QT_PLUGIN_PATH: {qt_plugin_path}")

    # DPI 感知：让 Qt 正确处理高分屏缩放
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    # 关键：必须在 PyQt5 之前预加载 OnnxRuntime
    log("预加载 OnnxRuntime...")
    preload_onnxruntime()

    try:
        log("导入 pdf2zh.gui_pyqt5...")
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QApplication
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        from pdf2zh.gui_pyqt5 import PDF2ZHMainWindow
        log("导入成功，启动 GUI...")

        app = QApplication(sys.argv)
        app.setStyle('Fusion')

        # ── 单实例检测：防止重复启动多个窗口 ──
        from PyQt5.QtNetwork import QLocalServer, QLocalSocket
        import hashlib
        _instance_key = "paperroute-" + hashlib.sha256(str(DATA_DIR).casefold().encode("utf-8")).hexdigest()[:24]
        _socket = QLocalSocket()
        _socket.connectToServer(_instance_key)
        if _socket.waitForConnected(500):
            # Ask the original instance to restore itself before this one exits.
            _socket.write(b"activate\n")
            _socket.flush()
            _socket.waitForBytesWritten(500)
            log("检测到已有实例运行，已发送窗口唤醒请求")
            _socket.close()
            sys.exit(0)
        _socket.close()
        _server = QLocalServer()
        _server.removeServer(_instance_key)
        _server.listen(_instance_key)
        log("单实例锁已创建")

        # ── DPI 感知样式表生成 ──
        dpr = app.primaryScreen().devicePixelRatio()
        log(f"DPI ratio: {dpr}")

        # DPR 补偿系数：高分屏上 Qt 会把逻辑像素放大到物理像素，
        # 导致同样 12px 在 4K@200% 屏显示为 24px 物理，视觉偏大。
        # 补偿公式：dpr>1 时缩小基准字号，使各屏幕物理显示大小接近。
        import builtins
        builtins._pdf2zh_dpr = dpr
        builtins._pdf2zh_dpr_scale = 1.0 / max(1.0, dpr ** 0.6)  # 高分屏更强补偿

        def build_stylesheet(base_font=12):
            from pdf2zh.paperroute_brand import stylesheet
            return stylesheet(base_font, getattr(builtins, "_pdf2zh_dpr_scale", 1.0))

        # 存为全局函数供字号切换时调用
        import builtins
        builtins._pdf2zh_build_stylesheet = build_stylesheet

        # 从用户配置读取上次字号，默认极小(10)
        _saved_font = 10
        try:
            import json as _json
            from pdf2zh.gui_pyqt5 import UserConfigManager
            _cfg_path = str(UserConfigManager.get_config_path())
            if os.path.exists(_cfg_path):
                with open(_cfg_path, 'r', encoding='utf-8') as _f:
                    _cfg = _json.load(_f)
                _level = _cfg.get('font_size_level', '极小')
                _saved_font = {'极小': 10, '小': 12, '中': 14, '大': 16, '极大': 18}.get(_level, 10)
        except Exception:
            pass
        log(f"初始字号: {_saved_font}px")
        app.setStyleSheet(build_stylesheet(_saved_font))
        window = PDF2ZHMainWindow()
        ensure_window_visible(window, app)

        def activate_pending_connections():
            while _server.hasPendingConnections():
                connection = _server.nextPendingConnection()
                show_main_window(window)
                connection.disconnectFromServer()
                connection.deleteLater()

        _server.newConnection.connect(activate_pending_connections)
        show_main_window(window)
        log("GUI 窗口已显示")
        sys.exit(app.exec_())
    except ImportError as e:
        msg = f"模块导入失败: {e}\n\n请检查 core\\site-packages 是否完整。"
        log(f"[ERROR] {msg}\n{traceback.format_exc()}")
        show_error_dialog("PaperRoute - 启动失败", msg)
        sys.exit(1)
    except Exception as e:
        msg = f"程序启动失败: {e}"
        log(f"[ERROR] {msg}\n{traceback.format_exc()}")
        show_error_dialog("PaperRoute - 运行错误", msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
