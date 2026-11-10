# PDF AI Translator

[简体中文](README.md) · [English](README.en.md)

A self-hosted PDF translation web app. Upload documents, choose a model service, track progress, and download translated or bilingual PDFs while preserving layout. Supports concurrent jobs, OCR, table handling, and reference skipping.

## Quick start

Install Docker and Docker Compose v2, then run from the project root:

```sh
docker compose up -d --build
```

Open **http://127.0.0.1:7000**:

1. Open **模型服务** (Model services), add a configuration, and activate it.
2. Upload PDFs, choose translation options, and click **开始翻译** (Start translation).
3. Download the results. Use `Clear` or `Clear all` when you no longer need the files.

The first build needs internet access to download dependencies, fonts, and layout models. Defaults: **2** concurrent jobs, **100 MiB** per PDF, automatic OCR enabled, and automatic glossary extraction disabled.

## Model services

| Type | Required fields |
| --- | --- |
| OpenAI compatible | Configuration name, Base URL, API Key, Model ID |
| Google Translate / Bing Translate | Configuration name |

Save multiple configurations and activate one. Switching or editing a configuration does not change submitted jobs. The form exposes JSON mode, thinking, and reasoning effort directly. Thinking parameters are inferred from the Model ID; custom aliases may not be recognized. Temperature is never sent. [Parameter details](server/doc/model-configuration.md)

For Ollama's OpenAI-compatible API on the Docker host, use `http://host.docker.internal:11434/v1`. Inside a container, `localhost` refers to that container. The model server must accept connections from the Docker network.

## Configuration

To customize a new installation, copy `.env.example` to `.env`, edit it, and rerun the startup command.

| Variable | Default | Description |
| --- | --- | --- |
| `BIND_ADDRESS` | `127.0.0.1` | Local access only; `0.0.0.0` enables remote access and requires login |
| `PORT` | `7000` | Host port |
| `ACCESS_PASSWORD` | `pdf2zh` | Remote access password |
| `MAX_CONCURRENT_TASKS` | `2` | Concurrent jobs, from 1 to 32 |
| `MAX_UPLOAD_MB` | `100` | Maximum PDF size in MiB |
| `SHUTDOWN_GRACE_SECONDS` | `600` | Seconds to wait for running jobs during shutdown |
| `COOKIE_SECURE` | `false` | Set to `true` when accessing over HTTPS |

For remote access, open `http://SERVER_IP:7000`. With a reverse proxy, keep the page and API on the same origin, disable buffering for `/events`, and allow long-lived connections.

```sh
docker compose logs -f pdf-ai-translator-server  # View service logs
docker compose down                           # Stop without deleting data
```

The Compose project is `pdf-ai-translator`. Both the service and container are named `pdf-ai-translator-server`. The image is `pdf-ai-translator-server:latest`.

## Offline deployment

Build and export on an internet-connected machine with the same CPU architecture as the server:

```sh
docker compose build
docker save pdf-ai-translator-server:latest | gzip > pdf-ai-translator-server.tar.gz
```

Copy the image archive, `compose.yaml`, and your optional `.env` to the server, then run:

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

[Development and tests](server/doc/development.md) · [Table handling](server/doc/table-modes.md) · [Reference skipping](server/doc/reference-skip.md)

Adapted from [zotero-pdf2zh](https://github.com/guaguastandup/zotero-pdf2zh), using [PDFMathTranslate Next](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next) and [BabelDOC](https://github.com/funstory-ai/BabelDOC) as its translation engine. License: [AGPL-3.0](LICENSE).
