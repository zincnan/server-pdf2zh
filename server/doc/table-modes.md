# 表格处理

网页的表格模式对应 `tableMode`，只使用 Python next 引擎。

- 空值：原生处理；可另启用 `translateTableText`。
- `preserve`：保留表格原文，不对表格文字进行翻译与重排。
- `fixed`：翻译文字单元格，尽量保持原单元格边界；数字、公式、代码与图形区域保守处理。

增强模式会覆盖原生表格文字开关。适配器在独立引擎子进程及其工作进程中安装和卸载策略，不修改已安装的 BabelDOC 源码。版本不在已验证范围时回退原生表格处理，提示写入任务日志。

`table_runtime.py` 组织策略；`table_process.py` 管理多进程钩子；`table_columns.py`、`table_geometry.py`、`table_layout.py`、`table_semantics.py` 等保留原有几何、语义和排版实现。

接口依赖 BabelDOC 内部 IL 对象。升级依赖时必须运行 `test_table_*`、真实引擎翻译以及人工核对表格 PDF。
