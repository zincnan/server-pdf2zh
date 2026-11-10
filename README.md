# PDF AI Translator

[简体中文](README.md) · [English](README.en.md)

可私有部署的 PDF 翻译 Web 应用。在浏览器上传文档、选择模型、查看进度，下载保留排版的译文或双语 PDF。支持多文件并发、OCR、表格处理和参考文献跳过。

## 快速开始

准备好 Docker 和 Docker Compose v2，在项目根目录执行：

```sh
docker compose up -d --build
```

打开 **http://127.0.0.1:7000**：

1. 在“模型服务”中添加配置并激活。
2. 上传 PDF，选择参数，点击“开始翻译”。
3. 完成后下载文件；不再需要时点击 `Clear` 或 `Clear all`。

首次构建需要联网下载依赖、字体和版面模型。默认同时翻译 **2** 个任务，每份文件最多 **100 MiB**；默认启用自动 OCR，关闭自动术语提取。

输出文件可多选，同时勾选“译文 PDF”和“双语 PDF”会生成两份文件。双语 PDF 可选“左右并排”或“交替分页”；裁剪选项主要适合双栏论文。

原文和译文语言均通过下拉框选择，可按中文名称或语言代码搜索。提供引擎列出的 153 个语言选项，常用语言优先显示，默认“英语 → 简体中文”。实际翻译效果取决于所选模型及引擎的字体、排版支持。

翻译参数修改后自动保存在服务端，刷新页面或重启服务时会恢复。语言、输出类型、布局和高级参数均会保留，`Clear` 不会删除这些设置；保存失败时会提示重试。当前为单用户服务，不同浏览器读取同一套设置。

## 模型服务

| 类型 | 需要填写 |
| --- | --- |
| OpenAI compatible | 配置名称、Base URL、API Key、Model ID |
| Google 翻译 / Bing 翻译 | 配置名称 |

可以保存多个配置并激活一个；切换或编辑配置不影响已提交任务。JSON 模式、思考开关和推理强度直接在表单中设置。思考参数按 Model ID 自动识别，自定义别名可能无法识别；不发送温度参数。[参数说明](server/doc/model-configuration.md)

连接宿主机 Ollama 的 OpenAI 兼容接口时，Base URL 使用 `http://host.docker.internal:11434/v1`；容器内的 `localhost` 指向容器自身。模型服务需允许来自 Docker 网段的连接。

## 部署设置

首次自定义配置时，将 `.env.example` 复制为 `.env` 并编辑，然后重新执行启动命令。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `BIND_ADDRESS` | `127.0.0.1` | 仅本机访问；设为 `0.0.0.0` 后允许远程访问并要求登录 |
| `PORT` | `7000` | 宿主机端口 |
| `ACCESS_PASSWORD` | `pdf2zh` | 远程访问密码 |
| `MAX_CONCURRENT_TASKS` | `2` | 同时执行的任务数，范围 1–32 |
| `MAX_UPLOAD_MB` | `100` | 单份 PDF 上限，单位 MiB |
| `SHUTDOWN_GRACE_SECONDS` | `600` | 停止服务时等待任务的秒数 |
| `COOKIE_SECURE` | `false` | 通过 HTTPS 访问时设为 `true` |

远程访问地址为 `http://服务器IP:7000`。使用反向代理时保持页面和 API 同源，为 `/events` 关闭缓冲并允许长连接。

```sh
docker compose logs -f pdf-ai-translator-server  # 查看服务日志
docker compose down                           # 停止服务，保留数据
```

Compose 项目名为 `pdf-ai-translator`，服务名与容器名均为 `pdf-ai-translator-server`，镜像为 `pdf-ai-translator-server:latest`。

## 离线部署

在与服务器 CPU 架构相同的联网机器上构建并导出：

```sh
docker compose build
docker save pdf-ai-translator-server:latest | gzip > pdf-ai-translator-server.tar.gz
```

将镜像包、`compose.yaml` 和按需配置的 `.env` 复制到服务器，再执行：

```sh
docker load -i pdf-ai-translator-server.tar.gz
docker compose up -d --no-build --pull never
```

服务器需提前安装 Docker 和 Compose。镜像已包含翻译引擎和静态资源，但翻译仍需能访问所选服务；完全离线时，请使用内网的 OpenAI 兼容模型服务。

## 数据与升级

默认数据卷为 **`pdf-ai-translator-data`**，挂载到 `/data`，保存模型配置、密钥、原文、结果和任务记录。

- 关闭网页不影响翻译。服务重启后保留已完成结果，中断任务可手动重新翻译，不保证断点续译。
- `Clear` 清理单个已结束任务的全部数据；`Clear all` 跳过运行中或下载中的任务。模型配置单独保存，不随任务清理。
- 任务不会自动过期。`docker compose down` 保留数据；`docker compose down -v` 会删除默认数据卷。
- 旧部署升级时，先停止旧容器，再在 `.env` 中设置 `DATA_VOLUME=原数据卷名称`、`DATA_VOLUME_EXTERNAL=true`，即可复用原数据。不要让两个实例同时使用同一数据卷。[迁移步骤](server/doc/deployment.md)

旧版模型配置会自动备份并迁移；不再支持的服务类型显示为“待转换”，编辑后再激活。

## 开发与来源

[开发与测试](server/doc/development.md) · [表格处理](server/doc/table-modes.md) · [参考文献跳过](server/doc/reference-skip.md)

基于 [zotero-pdf2zh](https://github.com/guaguastandup/zotero-pdf2zh) 改造，翻译引擎使用 [PDFMathTranslate Next](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next) 和 [BabelDOC](https://github.com/funstory-ai/BabelDOC)。许可证：[AGPL-3.0](LICENSE)。
