# PDF AI Translator

[简体中文](README.md) · [English](README.en.md)

A self-hosted PDF translation web app. Upload documents, choose a model service, track progress, and download translated or bilingual PDFs while preserving layout. Supports concurrent jobs, OCR, table handling, and reference skipping.

## Quick start

Install Docker and Docker Compose v2. Use the published image without cloning or building the source. For a new installation, download the [image deployment configuration](compose.image.yaml) as `compose.yaml` and [.env.example](.env.example) as `.env`:

```sh
mkdir -p pdf-ai-translator
cd pdf-ai-translator
curl -fsSL https://raw.githubusercontent.com/zincnan/server-pdf2zh/main/compose.image.yaml -o compose.yaml
test -f .env || curl -fsSL https://raw.githubusercontent.com/zincnan/server-pdf2zh/main/.env.example -o .env
```

**Edit `.env` before starting**: `PORT` sets the host port; `BIND_ADDRESS=127.0.0.1` allows local access, while `0.0.0.0` enables LAN access; `ACCESS_PASSWORD` sets the login password. [Configuration example](#configuration)

Save the file, then start:

```sh
docker compose pull
docker compose up -d
```

`docker compose pull` downloads `ghcr.io/zincnan/pdf-ai-translator-server:latest`; `up -d` starts the service. A separate `docker pull` is unnecessary. Prefer plain Docker? See [docker run](server/doc/deployment.md#docker-without-compose).

The default address is **http://127.0.0.1:7000**. For LAN access, open `http://SERVER_IP:PORT`, using the `PORT` from `.env`:

1. Open **模型服务** (Model services), add a configuration, and activate it.
2. Upload PDFs, choose translation options, and click **开始翻译** (Start translation).
3. Download the results. Use `Clear` or `Clear all` when you no longer need the files.

The image includes dependencies, fonts, and layout models. Translation still needs access to the selected model service. Defaults: **2** concurrent jobs, **100 MiB** per PDF, automatic OCR enabled, and automatic glossary extraction disabled.

The release workflow builds and tests `linux/amd64` (64-bit Intel/AMD) and `linux/arm64`, then combines them under the same image tags. Docker selects the matching architecture automatically. Older single-architecture images must be republished before ARM64 can pull them.

Output types can be selected together: choosing both **译文 PDF** (translated PDF) and **双语 PDF** (bilingual PDF) produces two files. Bilingual layouts support side-by-side or alternating pages. The crop options split two-column papers into individual columns.

Choose source and target languages from searchable dropdowns with Chinese labels and all 153 language options listed by the engine. Search by Chinese name or language code. Common languages appear first; the default is English → Simplified Chinese. Results depend on the selected model and the engine's font and layout support.

Translation options save automatically on the server. Languages, output types, layouts, and advanced options survive page reloads and service restarts. `Clear` does not remove preferences; a retry prompt appears if saving fails. This is currently a single-user service; all browsers load the same saved settings.

## Model services

| Type | Required fields |
| --- | --- |
| OpenAI compatible | Configuration name, Base URL, API Key, Model ID |
| Google Translate / Bing Translate | Configuration name |

Save multiple configurations and activate one. Switching or editing a configuration does not change submitted jobs. The form exposes JSON mode, thinking, and reasoning effort directly. Thinking parameters are inferred from the Model ID; custom aliases may not be recognized. Temperature is never sent. [Parameter details](server/doc/model-configuration.md)

For Ollama's OpenAI-compatible API on the Docker host, use `http://host.docker.internal:11434/v1`. Inside a container, `localhost` refers to that container. The model server must accept connections from the Docker network.

## Configuration

Compose automatically reads `.env` beside `compose.yaml`; the quick start downloads the template for you. This example enables LAN access and changes the host port to **8080**, without editing the Compose file:

```dotenv
BIND_ADDRESS=0.0.0.0
PORT=8080
ACCESS_PASSWORD=your-password
```

Save the changes and run `docker compose up -d`, then open `http://SERVER_IP:8080` and log in with the configured password. `PORT` changes the host port; the container continues to listen on 7000.

| Variable | Default | Description |
| --- | --- | --- |
| `IMAGE` | `ghcr.io/zincnan/pdf-ai-translator-server:latest` | Image deployment only; use `ghcr.io/zincnan/pdf-ai-translator-server:1.0.0` to pin a version |
| `BIND_ADDRESS` | `127.0.0.1` | Local access only; `0.0.0.0` enables remote access and requires login |
| `PORT` | `7000` | Host port |
| `ACCESS_PASSWORD` | `pdf2zh` | Remote access password |
| `MAX_CONCURRENT_TASKS` | `2` | Concurrent jobs, from 1 to 32 |
| `MAX_UPLOAD_MB` | `100` | Maximum PDF size in MiB |
| `SHUTDOWN_GRACE_SECONDS` | `600` | Seconds to wait for running jobs during shutdown |
| `COOKIE_SECURE` | `false` | Set to `true` when accessing over HTTPS |

With a reverse proxy, keep the page and API on the same origin, disable buffering for `/events`, and allow long-lived connections.

```sh
docker compose logs -f pdf-ai-translator-server  # View service logs
docker compose down                           # Stop without deleting data
```

The Compose project is `pdf-ai-translator`. Both the service and container are named `pdf-ai-translator-server`. Image deployments use GHCR; source builds produce the local image `pdf-ai-translator-server:latest`.

Update an image deployment:

```sh
docker compose pull
docker compose up -d
```

For a pinned version, change `IMAGE` in `.env` first. Updates reuse the existing data volume.

## Offline deployment

On an internet-connected machine, specify the target server's architecture before exporting the image. This example targets ARM64; substitute `linux/amd64` for an AMD64 server:

```sh
docker pull --platform linux/arm64 ghcr.io/zincnan/pdf-ai-translator-server:latest
docker save ghcr.io/zincnan/pdf-ai-translator-server:latest | gzip > pdf-ai-translator-server.tar.gz
```

Copy the image archive, [compose.image.yaml](compose.image.yaml), and your configured `.env` to the server. Save `compose.image.yaml` as `compose.yaml`, then run:

```sh
docker load -i pdf-ai-translator-server.tar.gz
docker compose up -d --no-build --pull never
```

Docker and Compose must already be installed on the server. The image includes the engine and static assets, but translation still needs access to the selected service. For a fully offline server, use an OpenAI-compatible model endpoint on your private network.

## Data and upgrades

The default volume, **`pdf-ai-translator-data`**, is mounted at `/data`. It stores model configurations, credentials, source documents, results, and job records.

- Closing the browser does not stop translation. Completed results survive service restarts; interrupted jobs can be retried manually, without guaranteed checkpoint resume.
- `Clear` removes all data for one finished job. `Clear all` skips running jobs and active downloads. Model configurations are managed separately.
- Jobs do not expire automatically. `docker compose down` keeps data; `docker compose down -v` deletes the default data volume.
- When upgrading an older deployment, stop its container first. Set `DATA_VOLUME=YOUR_EXISTING_VOLUME` and `DATA_VOLUME_EXTERNAL=true` in `.env` to reuse the data. Never run two instances against the same volume. [Migration steps](server/doc/deployment.md)

Older model configurations are backed up and migrated automatically. Unsupported service types remain available for manual conversion before activation.

## Development and credits

To build from source, clone the repository and use its root `compose.yaml`:

```sh
git clone https://github.com/zincnan/server-pdf2zh.git
cd server-pdf2zh
test -f .env || cp .env.example .env
docker compose up -d --build
```

The first build needs internet access to download dependencies, fonts, and layout models.

[Development and tests](server/doc/development.md) · [Table handling](server/doc/table-modes.md) · [Reference skipping](server/doc/reference-skip.md)

Adapted from [zotero-pdf2zh](https://github.com/guaguastandup/zotero-pdf2zh), using [PDFMathTranslate Next](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next) and [BabelDOC](https://github.com/funstory-ai/BabelDOC) as its translation engine. License: [AGPL-3.0](LICENSE).
