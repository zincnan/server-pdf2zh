# PDF AI Translator

<p align="center">
  <strong>专为学术论文、专业报告与外文书籍打造的私有化 PDF 智能翻译工作台</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-AGPL--3.0-blue.svg?style=flat-square" alt="License"></a>
  <a href="https://github.com/zincnan/server-pdf2zh/pkgs/container/pdf-ai-translator-server"><img src="https://img.shields.io/badge/Docker-ghcr.io-2496ED?logo=docker&logoColor=white&style=flat-square" alt="Docker Image"></a>
  <img src="https://img.shields.io/badge/Platform-linux%2Famd64%20%7C%20linux%2Farm64-brightgreen?style=flat-square" alt="Platform">
  <a href="https://github.com/zincnan/server-pdf2zh/stargazers"><img src="https://img.shields.io/github/stars/zincnan/server-pdf2zh?style=flat-square&logo=github" alt="GitHub Stars"></a>
</p>

<p align="center">
  <a href="README.md">简体中文</a> · <a href="README.en.md">English</a>
</p>

---

**PDF AI Translator** 是一款支持一键私有化部署的 PDF 智能翻译 Web 应用。通过深度集成先进翻译引擎与大语言模型，在完整保留原文排版、数学公式、图表布局的前提下，为您输出高质量的单语译文或双语对照 PDF。支持双栏学术论文智能拆分、多文件并发处理以及完全离线的私有环境部署。

---

## ✨ 核心特性

- 📑 **完美排版保留**：精准还原原文版面布局、字体层级、数学公式与图表位置，告别翻译后格式错乱的烦恼。
- 📖 **多元双语排版**：
  - **译文 PDF**：纯译文精读模式，完整继承原版式。
  - **双语对照**：支持同页“左右并排”或“交替分页”，阅读对比得心应手。
  - **双栏论文裁剪**：针对学术论文的双栏版式智能切分，生成适合平板与手机阅读的单栏流。
- 🌐 **153+ 全球语种支持**：内置主流与小众语言库，支持按中文名称或 ISO 代码即时搜索，常用语种置顶。
- 🤖 **全模型生态兼容**：
  - 兼容 OpenAI 标准 API，可无缝接入 DeepSeek、GPT-4o、Claude、Qwen、GLM 等主流模型。
  - 完美支持本地宿主机或内网部署的 **Ollama** 与 **vLLM**，实现完全本地化、零数据外泄的隐私翻译。
  - 支持 **Thinking** 思维链推理开关与 JSON 结构化输出。
  - 内置 Google / Bing 免费机器翻译引擎兜底。
- ⚡ **生产就绪与开箱即用**：
  - **多任务并发**：支持多份文档批量上传，后台异步排队与翻译处理。
  - **高级文档处理**：内置自动 OCR 识别、表格语义还原，支持自动跳过文末参考文献（节约 Token 与处理时间）。
  - **配置自动记忆**：语言、布局及高级参数自动保存在服务端，刷新页面或服务重启无感恢复。
- 🔒 **私有化与完全离线**：容器内已打包字体与排版算法模型，支持纯局域网、物理离线机房部署。

---

## 🚀 快速开始

### 前置要求
确保本地已安装 [Docker](https://docs.docker.com/engine/install/) 与 [Docker Compose v2](https://docs.docker.com/compose/)（系统要求原生支持 `amd64` / `arm64` 架构）。

### 一键启动
推荐直接使用预构建的官方镜像，无需克隆代码或本地编译：

```sh
mkdir -p pdf-ai-translator && cd pdf-ai-translator
curl -fsSL https://raw.githubusercontent.com/zincnan/server-pdf2zh/main/compose.image.yaml -o compose.yaml
test -f .env || curl -fsSL https://raw.githubusercontent.com/zincnan/server-pdf2zh/main/.env.example -o .env
docker compose pull
docker compose up -d
```

> [!TIP]
> 如果不希望使用 Docker Compose，也可以直接使用 [docker run 独立运行](server/doc/deployment.md#docker-without-compose)。

### 网页操作（3 步上手）
启动完成后，在浏览器中打开 **http://127.0.0.1:7000**：

1. **添加模型服务**：点击顶部导航栏的“模型服务”，添加并激活您的 AI 模型配置。
2. **上传文档与配置参数**：拖放上传一份或多份 PDF，选择源语言、目标语言及输出格式，点击“开始翻译”。
3. **下载结果**：翻译在后台自动进行（关闭网页不影响任务进度）。完成后点击即可下载译文；文档不再需要时可点击 `Clear` 或 `Clear all` 清理记录。

---

## 🤖 模型服务配置

您可以在 Web 界面保存多套模型配置并自由切换（切换配置不会影响正在运行的翻译任务）。

| 服务类型 | 必填项 | 适用场景与范例 |
| :--- | :--- | :--- |
| **OpenAI compatible** | 配置名称、Base URL、API Key、Model ID | DeepSeek、OpenAI、Claude、Kimi、Ollama、vLLM、硅基流动等 |
| **Google 翻译 / Bing 翻译** | 配置名称 | 免 API 密钥的通用快速机器翻译 |

### 常见模型配置范例

#### 1. DeepSeek 官方 API
- **Base URL**：`https://api.deepseek.com`
- **Model ID**：`deepseek-chat` 或 `deepseek-reasoner`（推理模型自动识别 Thinking 参数）

#### 2. 本地宿主机 Ollama
当服务运行在 Docker 容器中时，若 Ollama 安装在宿主机上，请勿填写 `localhost`（其指向容器自身），需使用 Docker 桥接域名：
- **Base URL**：`http://host.docker.internal:11434/v1`
- **API Key**：可随意填写任意非空字符（如 `ollama`）
- **Model ID**：您的本地模型名称（例如 `qwen2.5:7b`）
- *注意：宿主机 Ollama 需监听 `0.0.0.0` 或允许 Docker 网段访问。*

> 更多关于思考开关、参数调优与服务商兼容性，请参阅 [模型配置深度说明](server/doc/model-configuration.md)。

---

## ⚙️ 部署设置与常用命令

Docker Compose 会自动读取 `compose.yaml` 同级目录下的 `.env` 文件。

### 开启局域网远程访问与修改端口
编辑同目录的 `.env`：

```dotenv
BIND_ADDRESS=0.0.0.0       # 允许局域网/公网访问
PORT=8080                  # 将外部访问端口修改为 8080
ACCESS_PASSWORD=your_password  # 设置强访问密码（开启远程访问时强制要求登录）
```

保存后执行以下命令重新加载配置（保留原数据卷）：

```sh
docker compose up -d
```

### 核心环境变量速查

| 环境变量 | 默认值 | 作用与说明 |
| :--- | :--- | :--- |
| `IMAGE` | `ghcr.io/zincnan/pdf-ai-translator-server:latest` | 容器镜像版本，固定版本可写为具体 tag |
| `BIND_ADDRESS` | `127.0.0.1` | 绑定 IP。设为 `0.0.0.0` 开放外网访问并强制密码鉴权 |
| `PORT` | `7000` | 宿主机映射访问端口（容器内部端口固定为 7000） |
| `ACCESS_PASSWORD` | `pdf2zh` | 远程访问身份验证密码 |
| `MAX_CONCURRENT_TASKS` | `2` | 同时执行的最大翻译任务数（范围 1–32） |
| `MAX_UPLOAD_MB` | `100` | 单份上传 PDF 最大文件尺寸（单位 MiB） |
| `SHUTDOWN_GRACE_SECONDS`| `600` | 服务优雅停机等待任务结束的缓冲秒数 |
| `COOKIE_SECURE` | `false` | 若在反向代理后使用 HTTPS，请设为 `true` |

### 日常运维命令

```sh
docker compose logs -f pdf-ai-translator-server  # 实时查看服务日志
docker compose down                           # 停止并移除容器（数据卷保留）
docker compose pull && docker compose up -d    # 一键拉取最新镜像平滑升级
```

> [!NOTE]
> **反向代理配置要点**：若在 Nginx 等反代工具后运行，请保证 Web 页面与 API 同源，并为 `/events` 服务端事件流（SSE）**关闭代理缓冲**（`proxy_buffering off;`）并允许长连接。

---

## 📦 离线环境部署

针对无外网连接的保密内网或隔离机房，可在联网机器上打包镜像后导入目标服务器：

1. **联网机器导出镜像**（以 ARM64 目标机为例，AMD64 请替换为 `linux/amd64`）：
   ```sh
   docker pull --platform linux/arm64 ghcr.io/zincnan/pdf-ai-translator-server:latest
   docker save ghcr.io/zincnan/pdf-ai-translator-server:latest | gzip > pdf-ai-translator-server.tar.gz
   ```

2. **传输并加载到离线服务器**：
   将 `pdf-ai-translator-server.tar.gz`、[compose.image.yaml](compose.image.yaml) 以及 `.env` 复制到离线服务器。将 `compose.image.yaml` 命名为 `compose.yaml`，执行：
   ```sh
   docker load -i pdf-ai-translator-server.tar.gz
   docker compose up -d --no-build --pull never
   ```

> 离线环境下请配合内网自建的 OpenAI 兼容端点（如内网 Ollama / vLLM）进行翻译。

---

## 💾 数据持久化与升级

默认创建持久化数据卷 **`pdf-ai-translator-data`**，挂载到容器内部 `/data`，负责存储模型密钥、历史任务、原文及翻译产物。

- **后台持久运行**：关闭浏览器不中断翻译；重启容器后已完成结果完好保留，中断任务支持一键重新翻译。
- **安全清理机制**：`Clear` 清理单个已结束任务的数据；`Clear all` 仅清理非运行中的历史记录，模型配置始终独立存储，永不随任务丢失。
- **数据保留**：`docker compose down` 会保留所有任务与配置数据；请勿随意使用 `docker compose down -v`（`-v` 会销毁数据卷）。
- **历史版本升级迁移**：如需接入旧数据卷，停止旧容器后在 `.env` 中设置 `DATA_VOLUME=原数据卷名称` 与 `DATA_VOLUME_EXTERNAL=true` 即可平滑复用。[详细迁移指南](server/doc/deployment.md)

---

## 📈 Star History

如果您觉得本项目对您的工作或研究有所帮助，欢迎点亮右上角的 🌟 **Star** 支持我们！

[![Star History Chart](https://api.star-history.com/svg?repos=zincnan/server-pdf2zh&type=Date)](https://star-history.com/#zincnan/server-pdf2zh&Date)

---

## 🛠️ 源码开发与鸣谢

### 从源码运行
如需二次开发或基于源码调试：

```sh
git clone https://github.com/zincnan/server-pdf2zh.git
cd server-pdf2zh
test -f .env || cp .env.example .env
docker compose up -d --build
```

### 文档导航
- [开发环境搭建与单元测试](server/doc/development.md)
- [表格翻译处理模式详解](server/doc/table-modes.md)
- [参考文献智能跳过机制](server/doc/reference-skip.md)
- [错误排查与状态代码字典](server/doc/error-catalog.md)

### 致谢与开源协议
本项目基于 [zotero-pdf2zh](https://github.com/guaguastandup/zotero-pdf2zh) 改造，核心翻译能力依赖优秀的开源项目 [PDFMathTranslate Next](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next) 与 [BabelDOC](https://github.com/funstory-ai/BabelDOC)。

本项目遵循 [AGPL-3.0 许可证](LICENSE)。
