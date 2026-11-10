# PDF AI Translator

<p align="center">
  <strong>A self-hosted, layout-preserving PDF translation web platform designed for academic papers, technical reports, and books.</strong>
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

**PDF AI Translator** is a self-hosted web application for intelligent PDF translation. By combining specialized translation engines with modern Large Language Models, it translates entire PDF documents while preserving original typography, mathematical formulas, table structures, and page geometry. It outputs clean translated PDFs or bilingual reading versions, supports automatic two-column paper splitting, handles concurrent batch jobs, and is fully deployable in offline air-gapped environments.

---

## ✨ Key Features

- 📑 **Flawless Layout Preservation**: Retains font sizing, line spacing, mathematical formulas, and image positions without broken formatting or text overflows.
- 📖 **Flexible Bilingual Reading Modes**:
  - **Translated PDF**: Clean monolingual output preserving the original formatting.
  - **Bilingual Layouts**: Side-by-side (left/right) or alternating pages (top/bottom) for effortless comparative reading.
  - **Two-Column Paper Cropping**: Automatically splits dual-column research papers into mobile/tablet-friendly single-column pages.
- 🌐 **153+ Worldwide Languages**: Extensive language library with instant search by name or ISO language code.
- 🤖 **Universal LLM & Model Support**:
  - Standard OpenAI-compatible API support for DeepSeek, GPT-4o, Claude, Qwen, GLM, and more.
  - Seamless integration with local **Ollama** or **vLLM** instances for 100% private, air-gapped translation with zero data leakage.
  - Direct support for **Thinking / Reasoning Effort** controls and JSON structured output.
  - Built-in zero-configuration Google Translate and Bing Translate fallback engines.
- ⚡ **Production-Ready & Effortless**:
  - **Multi-File Batch Concurrency**: Upload multiple PDFs simultaneously with asynchronous background queuing.
  - **Smart Preprocessing**: Automatic OCR recognition, table reconstruction, and intelligent reference skipping (saves tokens and runtime).
  - **Automatic Preference Persistence**: Language choices, layout modes, and advanced tuning are saved server-side across reloads and restarts.
- 🔒 **Private & Fully Air-Gapped**: Bundles dependencies, fonts, and layout models inside the container for strictly isolated private deployments.

---

## 🚀 Quick Start

### Prerequisites
Make sure you have [Docker](https://docs.docker.com/engine/install/) and [Docker Compose v2](https://docs.docker.com/compose/) installed (native support for both `amd64` and `arm64`).

### One-Click Launch
Use the official pre-built image—no need to clone source code or build locally:

```sh
mkdir -p pdf-ai-translator && cd pdf-ai-translator
curl -fsSL https://raw.githubusercontent.com/zincnan/server-pdf2zh/main/compose.image.yaml -o compose.yaml
test -f .env || curl -fsSL https://raw.githubusercontent.com/zincnan/server-pdf2zh/main/.env.example -o .env
docker compose pull
docker compose up -d
```

> [!TIP]
> Prefer running without Docker Compose? Check the [docker run standalone guide](server/doc/deployment.md#docker-without-compose).

### Web UI (3-Step Walkthrough)
Once started, navigate to **http://127.0.0.1:7000** in your browser:

1. **Add Model Service**: Click **模型服务** (Model services) in the top bar to configure and activate your AI model.
2. **Upload & Configure**: Drag and drop one or more PDFs, choose source/target languages and output formats, then click **开始翻译** (Start translation).
3. **Download Results**: Translation runs asynchronously in the background (closing your browser will not interrupt progress). When finished, download your documents. Clean up completed jobs anytime with `Clear` or `Clear all`.

---

## 🤖 Model Services Setup

You can save multiple model presets and toggle between them (switching active presets does not affect already queued or running jobs).

| Service Type | Required Fields | Use Cases & Examples |
| :--- | :--- | :--- |
| **OpenAI compatible** | Configuration Name, Base URL, API Key, Model ID | DeepSeek, OpenAI, Claude, Kimi, Ollama, vLLM, SiliconFlow, etc. |
| **Google Translate / Bing Translate** | Configuration Name | Free general-purpose machine translation (no API key required) |

### Common Presets

#### 1. DeepSeek Official API
- **Base URL**: `https://api.deepseek.com`
- **Model ID**: `deepseek-chat` or `deepseek-reasoner` (thinking mode is recognized automatically)

#### 2. Local Host Ollama
When running this service inside Docker, use the Docker host gateway instead of `localhost` (which refers to the container itself):
- **Base URL**: `http://host.docker.internal:11434/v1`
- **API Key**: Any non-empty string (e.g., `ollama`)
- **Model ID**: Your pulled model tag (e.g., `qwen2.5:7b`)
- *Note: Ensure your host Ollama is listening on `0.0.0.0` or allows connections from Docker networks.*

> For thinking controls, custom parameters, and provider specifics, see [Model Configuration Guide](server/doc/model-configuration.md).

---

## ⚙️ Configuration & Operations

Docker Compose reads environment variables from `.env` in the same directory as `compose.yaml`.

### Remote Access & Port Binding
Edit `.env` in your deployment directory:

```dotenv
BIND_ADDRESS=0.0.0.0       # Allow LAN or public network access
PORT=8080                  # Change external port to 8080
ACCESS_PASSWORD=your_password  # Set a strong password (required for remote access)
```

Apply changes immediately while preserving your existing data volume:

```sh
docker compose up -d
```

### Environment Variables Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `IMAGE` | `ghcr.io/zincnan/pdf-ai-translator-server:latest` | Container image tag; set to a specific tag (e.g. `1.0.0`) to pin versions |
| `BIND_ADDRESS` | `127.0.0.1` | Bind address. Change to `0.0.0.0` for remote access (enforces password login) |
| `PORT` | `7000` | Host port exposed to clients (container always listens on 7000 internally) |
| `ACCESS_PASSWORD` | `pdf2zh` | Authentication password for remote access |
| `MAX_CONCURRENT_TASKS` | `2` | Maximum concurrent translation jobs (range: 1–32) |
| `MAX_UPLOAD_MB` | `100` | Maximum file upload limit per PDF (in MiB) |
| `SHUTDOWN_GRACE_SECONDS`| `600` | Grace period in seconds to wait for active jobs during container stop |
| `COOKIE_SECURE` | `false` | Set to `true` when accessing through an HTTPS reverse proxy |

### Useful Maintenance Commands

```sh
docker compose logs -f pdf-ai-translator-server  # Tail real-time service logs
docker compose down                           # Stop and remove containers (keeps data volume)
docker compose pull && docker compose up -d    # Pull latest image and smoothly update
```

> [!NOTE]
> **Reverse Proxy Tips**: When placing behind Nginx or another reverse proxy, maintain the same origin for static assets and API requests, and **disable proxy buffering** (`proxy_buffering off;`) on the `/events` Server-Sent Events (SSE) stream.

---

## 📦 Offline Air-Gapped Deployment

For air-gapped workstations or private secure servers:

1. **Export Image on an Internet-Connected Machine** (replace `linux/arm64` with `linux/amd64` if targeting AMD64):
   ```sh
   docker pull --platform linux/arm64 ghcr.io/zincnan/pdf-ai-translator-server:latest
   docker save ghcr.io/zincnan/pdf-ai-translator-server:latest | gzip > pdf-ai-translator-server.tar.gz
   ```

2. **Transfer & Load on Target Server**:
   Copy `pdf-ai-translator-server.tar.gz`, [compose.image.yaml](compose.image.yaml), and your configured `.env` to the destination server. Rename `compose.image.yaml` to `compose.yaml`, then run:
   ```sh
   docker load -i pdf-ai-translator-server.tar.gz
   docker compose up -d --no-build --pull never
   ```

> For completely offline environments, configure an internal OpenAI-compatible endpoint (such as an internal Ollama or vLLM server).

---

## 💾 Data Persistence & Upgrades

The default Docker volume **`pdf-ai-translator-data`** mounts to `/data` in the container, persistently storing model credentials, task histories, uploaded documents, and translated outputs.

- **Background Reliability**: Closing your browser will not terminate active translations. Completed files persist across container restarts, and interrupted tasks can be retried manually.
- **Safe Task Cleanup**: `Clear` deletes files for a specific finished job; `Clear all` cleans up all non-running history. Model configurations are stored independently and are never wiped by clearing jobs.
- **Volume Safety**: `docker compose down` retains all your data. Avoid running `docker compose down -v` unless you intentionally want to delete the data volume.
- **Upgrading from Older Deployments**: Stop the old container, set `DATA_VOLUME=YOUR_OLD_VOLUME` and `DATA_VOLUME_EXTERNAL=true` in `.env`, and launch the new instance. See the [Migration Guide](server/doc/deployment.md) for details.

---

## 📈 Star History

If you find this project helpful for your workflow or research, please consider giving us a 🌟 **Star**!

[![Star History Chart](https://api.star-history.com/svg?repos=zincnan/server-pdf2zh&type=Date)](https://star-history.com/#zincnan/server-pdf2zh&Date)

---

## 🛠️ Development & Credits

### Build from Source
To run and develop locally from source:

```sh
git clone https://github.com/zincnan/server-pdf2zh.git
cd server-pdf2zh
test -f .env || cp .env.example .env
docker compose up -d --build
```

### Documentation Index
- [Development Setup & Tests](server/doc/development.md)
- [Table Translation Modes](server/doc/table-modes.md)
- [Automatic Reference Skipping](server/doc/reference-skip.md)
- [Error Codes & Troubleshooting Catalog](server/doc/error-catalog.md)

### Acknowledgements & License
Adapted from [zotero-pdf2zh](https://github.com/guaguastandup/zotero-pdf2zh). The core layout translation engine is powered by the open-source projects [PDFMathTranslate Next](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next) and [BabelDOC](https://github.com/funstory-ai/BabelDOC).

Licensed under the [AGPL-3.0 License](LICENSE).
