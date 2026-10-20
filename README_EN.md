# PaperRoute

A Windows PDF translation variant with batch processing, model failover and a compact reading workspace.

[Download](https://github.com/508liang/PaperRoute/releases/tag/v0.1.0) · [Alibaba Cloud setup](docs/ALIYUN.md) · [Build notes](docs/BUILDING.md)

Run `PaperRoute.exe`, open **管理模型**, add your models, and save with the green button. **添加阿里云** prefills an Alibaba Cloud Model Studio example using `qwen-plus`; supply your own API key. You can also copy the OpenAI-compatible API endpoint from the Model Studio console. See the [official compatibility guide](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope).

Select multiple PDFs or a folder. Files are processed sequentially; paragraphs use the configured concurrency. Timeout, HTTP errors and empty replies trigger model failover. Completed paragraphs are cached. Closing unsaved model settings prompts Save / Discard / Continue editing.

The single exe expands its runtime once into `%LOCALAPPDATA%/PaperRoute/runtime/`. User settings and PDFs remain separate in `%LOCALAPPDATA%/PaperRoute/`. No personal keys or PDFs are embedded in the release. Build checks use a mock server and synthetic PDFs.

Developed by [508liang](https://github.com/508liang) with Codex. The engine is based on [PDFMathTranslate](https://github.com/PDFMathTranslate/PDFMathTranslate); the desktop shell is adapted from [AaronGIG/pdf2zh-desktop](https://github.com/AaronGIG/pdf2zh-desktop), with [BabelDOC](https://github.com/funstory-ai/BabelDOC) dependencies. License and component details are available in [LICENSE](LICENSE), [LICENSE_SCOPE.md](LICENSE_SCOPE.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
