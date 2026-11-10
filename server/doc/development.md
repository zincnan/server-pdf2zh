# Development

PDF AI Translator uses Flask with Waitress and a pinned PDFMathTranslate Next / BabelDOC engine. Runtime jobs use separate subprocesses and workspaces. The Docker container runs as UID/GID 10001; `/data` must be writable by that user.

## Dependencies

The baseline is Python 3.12, pdf2zh-next 2.9.0, BabelDOC 0.6.4, and PyMuPDF 1.26.7. `server/requirements.txt` locks all Python dependencies and hashes.

next 2.9.0 declares `PyMuPDF<1.25.3`, while BabelDOC 0.6.4 requires `PyMuPDF>=1.26.7`. The explicit uv override in `server/overrides.txt` selects BabelDOC's renderer requirement. Install with that override; do not substitute a plain pip installation that ignores it.

Update `server/requirements.in` and regenerate the lock when changing dependencies:

```sh
uv pip compile --python-version 3.12 --override server/overrides.txt --generate-hashes server/requirements.in -o server/requirements.txt
```

The table and reference policies depend on upstream internal APIs. Engine upgrades require real PDF regression checks, not just successful imports.

## Validation

Run from the project root:

```sh
uv venv --python 3.12 .venv-test
uv pip install --python .venv-test/bin/python --override server/overrides.txt -r server/requirements.txt
PYTHONPATH=server .venv-test/bin/python -m unittest discover -s server/tests -p 'test_*.py' -v
node --check server/static/app.js
node --check server/static/language-picker.js
docker compose config --quiet
docker build -t pdf-ai-translator-server:latest .
docker run --rm -e PYTHONPATH=/app/server -e RUN_TRANSLATION_INTEGRATION=1 pdf-ai-translator-server:latest python -m unittest tests.test_translation_integration -v
```

The integration test uses the real PDF engine and a local mock model endpoint. It does not call a paid API. Static assets are prepared while building the image. Service request mutations require the `X-PDF-AI-Translator-Request: 1` header; access authentication also applies when enabled.

## Translation preferences

`GET /api/preferences` returns `{ "translationOptions": { ... } }`. `PATCH /api/preferences` accepts the same envelope with a partial options object and returns the merged settings. These single-user preferences live in `/data/config/preferences.json`, separately from jobs and model credentials. Missing fields inherit engine defaults. Empty output selections are valid drafts; job submission still requires a PDF output.

The browser saves valid changes automatically and only displays validation or save errors. Numeric fields debounce for 300 ms and flush on blur or page exit. Optional `writerId` and positive integer `sequence` fields identify updates from one page; the server ignores older updates to fields already saved at a higher sequence. This prevents a delayed request from reverting newer edits sent during a reload. Ordinary API clients can omit both fields. Ordering metadata is bounded in memory and is not part of the saved preferences.

## Naming

| Component | Name |
| --- | --- |
| Product | PDF AI Translator |
| Project ID / Compose project | `pdf-ai-translator` |
| Compose service / container | `pdf-ai-translator-server` |
| Local image | `pdf-ai-translator-server:latest` |
| Default data volume | `pdf-ai-translator-data` |

Upstream package names such as `pdf2zh_next` and engine asset paths retain their engine-specific names. The explicitly configured default access password remains `pdf2zh`.
