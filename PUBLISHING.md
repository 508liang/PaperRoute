# 发布与许可说明

维护者选择将 PaperRoute 仓库公开发布，地址为 <https://github.com/508liang/PaperRoute>。此文件记录实际来源和许可边界，不声称已获得所有第三方部分的独立授权。

## 来源状态

2026-10-20 检查时，PDFMathTranslate 1.9.9 与 BabelDOC 0.2.33 随附 AGPL-3.0 许可证。AaronGIG/pdf2zh-desktop 的 GitHub API 返回 `license: null`，公开仓库及本机便携包中未找到明确覆盖其独立桌面外壳的许可证。

新增 PaperRoute 代码提供 AGPL-3.0-only 许可；这不改变原作者对既有代码的权利，也不代表不明确的第三方授权已经得到确认。保留来源声明与 LICENSE_SCOPE.md，不把整个仓库的所有文件一概宣称为已获得 AGPL 授权。后续若取得上游授权或替换相关实现，应补充对应依据。

参考：[原桌面项目](https://github.com/AaronGIG/pdf2zh-desktop)、[PDFMathTranslate 许可证](https://github.com/PDFMathTranslate/PDFMathTranslate/blob/main/LICENSE)、[BabelDOC 许可证](https://github.com/funstory-ai/BabelDOC/blob/main/LICENSE)、[GitHub 许可说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)。

## 发布内容

- Git 仓库只提交清理后的代码、文档、示例配置、界面示例图与许可证资料。
- 单文件 `PaperRoute.exe`、对应源码包和校验值放在 GitHub Releases；不把 exe 塞进 Git 历史。
- 标记为 0.1.0 预览版本，保留版本一致的源码和依赖清单。
- 不上传个人模型、密钥、历史、论文、译文、日志或备份。打包和源码导出均检查本机已配置的密钥不会进入发布文件。

运行 `core/runtime/python.exe scripts/build_single_file.py` 生成单文件；运行 `core/runtime/python.exe scripts/make_source_bundle.py` 生成白名单源码包。`PaperRoute-package.json` 记录载荷标识、体积及 SHA-256。

单文件首次展开到本机 `%LOCALAPPDATA%/PaperRoute/runtime/`，个人数据独立存储。附带的微软运行库、Python、Qt、PDF/图像依赖和字体保留各自版权与许可，不由项目根许可证重新许可。
