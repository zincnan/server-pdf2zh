# 跳过参考文献

`skipReferences` 默认为 false。启用后，识别出的参考文献段落保留原文，并从自动术语提取及翻译请求中排除。附录等后续章节继续翻译。实现依据标题和引文结构保守识别，不删除 PDF 内容。

当前验证组合为 pdf2zh-next 2.9.0 / BabelDOC 0.6.4。版本不匹配时回退原生翻译并记录提示。策略仅安装在当前引擎子进程中，并与表格策略共同作用。

该功能独立实现，其动机参考 [Reference Skip 讨论](https://github.com/qianzhouji/zotero-pdf2zh-patches)，保留来源说明，不依赖该项目代码或 Zotero。
