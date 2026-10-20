# PaperRoute 来源与许可记录

PaperRoute（选路译读）是基于已有 PDF 翻译桌面程序的衍生改版，不是上游官方版本，也不主张对原有代码或第三方组件的原创所有权。

| 部分 | 来源 | 已确认的许可状态 |
| --- | --- | --- |
| PDF 翻译核心，当前安装元数据版本 1.9.9 | [PDFMathTranslate / Byaidu 与贡献者](https://github.com/PDFMathTranslate/PDFMathTranslate) | 随附 AGPL-3.0 许可证，保留原声明 |
| 排版相关依赖，当前版本 0.2.33 | [BabelDOC / funstory-ai 与贡献者](https://github.com/funstory-ai/BabelDOC) | 随附 AGPL-3.0 许可证，保留原声明 |
| Windows 桌面外壳、原便携化及原桌面增强代码 | [AaronGIG / pdf2zh-desktop](https://github.com/AaronGIG/pdf2zh-desktop) | 目前未找到明确的独立桌面外壳 LICENSE；独立授权范围仍未确认，保留该许可边界记录 |
| 新增模型池、窗口唤醒、PaperRoute 品牌与主题、启动器及新增工具脚本 | PaperRoute contributors，2026 | 新增部分提供 AGPL-3.0-only 许可；不重新许可第三方代码 |
| Python、PyQt5、PyMuPDF、ONNX Runtime 及其他运行时依赖 | 各组件原作者 | 各自许可证继续适用；现有随附许可文件不删除 |
| 单文件版的简体中文译文字体 Source Han Serif CN Regular | [Adobe / source-han-serif](https://github.com/adobe-fonts/source-han-serif)；字体内部版权为 © 2017–2024 Adobe | SIL Open Font License 1.1；保留字体内部声明及 licenses/SourceHanSerif-OFL-1.1.txt |
| 单文件版的 Microsoft Visual C++ 运行库，AMD64 | 随原目录提供的 VC_redist.x64.exe 中的原始运行库 | 保留微软许可条款 licenses/Microsoft-VC-Runtime.rtf；不适用 AGPL，公开分发须符合相应微软授权 |

PaperRoute 的主要修改：模型池故障切换与独立限速、可见的并发线程设置、真正折叠的高级选项、更窄的侧栏、新品牌与图标、无推广入口、关闭 Zotero 与自动更新配置，以及重复启动时的窗口恢复。

后续界面调整包括使用系统自带的行楷字体显示标语、模型配置保存提醒，以及精简单文件 Windows 打包。系统行楷字体仅在运行时调用，不复制或随包分发；单文件版保留所带依赖的许可证和版权资料。

许可证原文位于 `licenses/`。根目录 LICENSE 仅声明新增 PaperRoute 代码的许可，不能解释为对许可状态未确认的原桌面外壳授予授权。发布前请先阅读 PUBLISHING.md。
