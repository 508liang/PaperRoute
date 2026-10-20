# 构建与验证

普通使用请下载 GitHub Releases 中的 `PaperRoute.exe`。仓库是桌面改版源码，不直接携带完整 Python 和数百 MB 的第三方二进制依赖。

## 运行环境

构建在 Windows x64 完整便携目录中执行，需要 `core/runtime`（Python 3.12）、相应 `core/site-packages`、`assets/doclayout_yolo.onnx`、`assets/fonts/SourceHanSerifCN-Regular.ttf` 和原运行环境提供的 `VC_redist.x64.exe`。精确已安装依赖版本随源码包的 `RUNTIME_VERSIONS.json` 记录；第三方组件来源和许可见仓库根目录说明。

依赖补齐后，将本仓库的 `core/site-packages/pdf2zh` 覆盖到对应运行目录。不要把上游更新直接覆盖到这些经过修改的文件。

## 构建命令

```powershell
.\core\runtime\python.exe .\scripts\build_icon.py
.\scripts\build_launcher.ps1
.\core\runtime\python.exe .\tests\test_local_edition.py
.\core\runtime\python.exe .\scripts\build_single_file.py
.\core\runtime\python.exe .\tests\verify_single_file.py
.\core\runtime\python.exe .\scripts\make_source_bundle.py
```

`build_single_file.py` 在干净目录展开候选载荷，检查 Qt、sip、ONNX 版面模型、PDF/OCR 依赖和中文字体后，再编译单文件 exe。微软运行库仅从原安装包展开到应用本地，不运行系统安装程序；保留原始条款。不会向 exe 写入个人配置。

`verify_single_file.py` 打开实际 Windows 窗口，检查可见性、缓存复用、保存区及关闭提醒，并用精简运行库与模拟接口翻译两份合成 PDF。测试不调用付费模型，结束后清理测试展开目录。

根目录 `PaperRoute.exe` 是完整便携目录的快速启动器；`release/PaperRoute.exe` 是可以单独分发的完整单文件包。源码、exe 和依赖版本应对应同一个发布版本。
