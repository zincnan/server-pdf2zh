FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DATA_DIR=/data ASSET_DIR=/opt/pdf2zh-assets UV_HTTP_TIMEOUT=300
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.9.4
WORKDIR /app
COPY server/requirements.txt server/overrides.txt /app/
RUN uv pip install --system --no-cache --override /app/overrides.txt -r /app/requirements.txt
COPY server/prepare_assets.py /opt/prepare_assets.py
# Download static resources at build time so concurrent jobs never race on a
# shared model download. Task caches only link these immutable asset files.
RUN python /opt/prepare_assets.py && \
    chmod -R a-w /opt/pdf2zh-assets && \
    useradd --uid 10001 --create-home pdftranslate && \
    mkdir -p /data && chown 10001:10001 /data
COPY server /app/server
USER 10001:10001
EXPOSE 8890
CMD ["python", "/app/server/server.py"]
