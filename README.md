# PDF Translate

独立、可私有部署的 PDF 翻译 Web 服务。基于 Flask、PDFMathTranslate Next 和 BabelDOC，复用 zotero-pdf2zh 中的翻译参数适配、进度解析、表格增强、参考文献跳过及裁剪排版实现，无需 Zotero。

支持浏览器上传 PDF、配置多个模型服务、激活一个配置、并发翻译、实时查看进度、下载或预览结果，以及按任务清理全部文档数据。

## 启动

需要 Docker Engine 和 Docker Compose：

```sh
docker compose up -d --build
```

打开 <http://127.0.0.1:8890>。首次构建会安装翻译引擎、下载字体和版面模型，需要联网；随后任务复用镜像中的静态资源。模型服务依然需要对应的网络连接或本机模型。

首次进入，在“模型服务”中添加服务商、API URL、API Key 和模型，保存并激活。也支持不需要密钥的引擎适配服务。上传一份或多份 PDF，选择参数后开始翻译。默认最多同时翻译 2 个任务，其他任务排队。

连接宿主机上的 Ollama 等服务时，使用 `http://host.docker.internal:11434`，不要使用指向容器自身的 `localhost`。宿主机服务需允许来自 Docker 网段的连接。

## 访问与部署配置

复制 `.env.example` 为 `.env` 后修改：

| 变量 | 默认值 | 含义 |
| --- | --- | --- |
| `BIND_ADDRESS` | `127.0.0.1` | 宿主机发布地址；`0.0.0.0` 开放网络访问并强制登录 |
| `PORT` | `8890` | 宿主机端口 |
| `ACCESS_PASSWORD` | `pdf2zh` | 网络访问密码 |
| `MAX_CONCURRENT_TASKS` | `2` | 同时执行的任务数，1–32；根据内存与模型额度调整 |
| `MAX_UPLOAD_MB` | `100` | 每份 PDF 大小上限，MiB |
| `SHUTDOWN_GRACE_SECONDS` | `600` | 停止时等待正在执行任务的秒数 |
| `COOKIE_SECURE` | `false` | 通过 HTTPS 反向代理访问时设为 `true` |

容器内部始终监听 `0.0.0.0:8890`；登录要求取决于显式传入的宿主机发布地址 `PUBLISHED_BIND_ADDRESS`，未声明时默认要求登录。使用 Compose 以外的启动方式时，需自行映射 `/data` 并传入对应配置。仅支持单实例独占同一个数据卷。

通过反向代理使用时保持同源访问，为 `/events` 禁用响应缓冲并允许长连接；不要将前端与 API 部署在不同源。服务不会在运行期自动升级、重载源码或安装依赖。

## 任务、重启与清理

- 刷新、关闭网页不会取消任务，重新打开即可查看状态。
- 原 PDF、生成文件、文档缓存、中间数据和任务清单保存在 Docker 的 `pdf2zh-data` 命名卷。
- 重启后已完成结果仍可下载；排队或运行中的任务标记为“已中断”，需要点击“重新翻译”。重试使用当前激活服务，重新执行整个文档，不保证断点续译。
- 正常停止会先拒绝新任务，最多等待配置的宽限时间。`docker kill`、断电和 OOM 等强制终止会中断正在执行的任务，但保留已经落盘的文件。
- `Clear` 删除一个已结束任务的原文、结果、中间数据、翻译缓存、日志和记录。`Clear all` 清理全部已结束任务，跳过运行中或正在下载的任务。
- **模型服务与 API Key 是服务配置，独立持久保存；清理任务不会删除它们。** API 查询不返回已保存密钥。编辑时留空保留密钥，勾选删除密钥可移除。
- 引擎运行时的临时配置可能包含凭据，文件仅服务进程可读写，结束后删除。任务错误与诊断日志脱敏后保存在任务目录，不将全文输出到容器日志。
- 不设置任务自动过期，也不在启动时删除未清理的正常任务。磁盘占用会随保留任务增加。
- `docker compose down` 保留命名卷；`docker compose down -v` 会删除包括模型配置在内的所有数据。

任务采用各自目录，允许同时上传同名文件。该产品是单机持久工作台，按任务手动清理；不是跨实例无状态服务。

## 翻译功能

仅使用 `pdf2zh_next`，保留仅译文、双语、LR 左右布局、TB 交替页、双栏裁剪、对照输出、OCR 兼容选项、表格模式和参考文献跳过。独立裁剪 API 和 Zotero 插件协议均已移除。

裁剪面向双栏论文，单栏文档通常无需启用。OCR、表格和公式的具体效果由文档及引擎能力决定。表格和参考文献扩展只在经过验证的引擎版本上启用。

## 依赖与验证

引擎基线：Python 3.12、pdf2zh-next 2.9.0、BabelDOC 0.6.4、PyMuPDF 1.26.7。`server/requirements.txt` 锁定完整依赖及哈希。

next 2.9.0 的发布元数据声明 `PyMuPDF<1.25.3`，而 BabelDOC 0.6.4 要求 `PyMuPDF>=1.26.7`。`server/overrides.txt` 显式选用 BabelDOC 所需的渲染器版本；Docker 使用 uv 安装并应用这一个覆盖。不能用忽略此覆盖的普通 pip 安装替代。

开发验证命令：

```sh
uv venv --python 3.12 .venv-test
uv pip install --python .venv-test/bin/python --override server/overrides.txt -r server/requirements.txt
PYTHONPATH=server .venv-test/bin/python -m unittest discover -s server/tests -p 'test_*.py' -v
node --check server/static/app.js
docker compose config --quiet
docker build -t pdf2zh-web:test .
```

更新依赖时编辑 `server/requirements.in`，重新生成锁文件并运行回归；不要直接放宽 BabelDOC 版本，因为表格与参考文献扩展使用了其内部接口。

## 来源

本项目基于 [guaguastandup/zotero-pdf2zh](https://github.com/guaguastandup/zotero-pdf2zh) 改造；翻译核心来自 [PDFMathTranslate Next](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next) 与 [BabelDOC](https://github.com/funstory-ai/BabelDOC)。保留原有 AGPL 许可证及相关来源说明，见 [LICENSE](LICENSE)。
