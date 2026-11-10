# Deployment and data migration

## Published image deployment

推荐使用 [README 的快速开始](../../README.md#快速开始)。只需下载 [compose.image.yaml](../../compose.image.yaml) 并保存为 `compose.yaml`，不需要源码或 Dockerfile；`.env` 是可选配置。`docker compose pull` 下载镜像，`docker compose up -d` 创建并启动容器。镜像默认使用 `ghcr.io/zincnan/pdf-ai-translator-server:latest`；在 `.env` 中设置 `IMAGE=ghcr.io/zincnan/pdf-ai-translator-server:1.0.0` 可固定版本。

Use the [README quick start](../../README.en.md#quick-start): download [compose.image.yaml](../../compose.image.yaml) as `compose.yaml`. Source code and a Dockerfile are unnecessary; `.env` is optional. Run `docker compose pull` followed by `docker compose up -d`. The default image is `ghcr.io/zincnan/pdf-ai-translator-server:latest`; set `IMAGE` in `.env` to pin a version.

维护者发布镜像后，需确保 GHCR 包的可见性为 **Public**，其他人才能免登录拉取。公开 GitHub 仓库与公开镜像包是两个独立设置。当前发布架构为 `linux/amd64`。

For anonymous pulls, maintainers must make the GHCR package **Public**. Repository and package visibility are independent. Published images currently target `linux/amd64`.

## Docker without Compose

不强制使用 Compose。只安装 Docker 时，也可以直接运行下面的命令；镜像不存在时会自动下载：

Compose is optional. With Docker alone, run the following command; Docker downloads the image if it is missing:

```sh
docker run -d \
  --name pdf-ai-translator-server \
  --init \
  --restart unless-stopped \
  --stop-timeout 620 \
  --publish 127.0.0.1:7000:7000 \
  --env PUBLISHED_BIND_ADDRESS=127.0.0.1 \
  --volume pdf-ai-translator-data:/data \
  --add-host host.docker.internal:host-gateway \
  --security-opt no-new-privileges:true \
  --cap-drop ALL \
  ghcr.io/zincnan/pdf-ai-translator-server:latest
```

打开 / Open **http://127.0.0.1:7000**。

远程访问时，将 `--publish` 的绑定地址和 `PUBLISHED_BIND_ADDRESS` 都改为 `0.0.0.0`，并添加 `--env ACCESS_PASSWORD=your-password`。命名数据卷会保存配置、密钥和文档。

For remote access, change both the published bind address and `PUBLISHED_BIND_ADDRESS` to `0.0.0.0`, and add `--env ACCESS_PASSWORD=your-password`. The named volume preserves settings, credentials, and documents.

## 旧部署迁移 / Moving an older deployment

改名后 Compose 项目和默认卷名称发生变化。旧数据不会自动移入新卷。以下步骤可直接复用原数据，不需要复制文档或重新配置密钥。

The renamed Compose project uses a new default volume name. To keep an older deployment's documents, results, and model profiles, reuse its existing volume rather than starting with an empty volume.

1. 找到旧容器及其 `/data` 卷 / Identify the old container and its `/data` volume:

   ```sh
   docker ps -a --format 'table {{.Names}}\t{{.Image}}'
   docker inspect OLD_CONTAINER --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}'
   ```

2. 任务完成后，停止旧容器 / Once running jobs finish, stop the old container:

   ```sh
   docker stop OLD_CONTAINER
   ```

3. 将上一步输出的实际卷名填入新项目的 `.env` / Set the actual volume name in the new project's `.env`:

   ```dotenv
   DATA_VOLUME=YOUR_EXISTING_VOLUME
   DATA_VOLUME_EXTERNAL=true
   ```

4. 使用镜像部署时，先拉取再启动；使用源码构建时执行 `docker compose up -d --build` / For an image deployment, pull and start; for a source build, use `docker compose up -d --build`:

   ```sh
   docker compose pull
   docker compose up -d
   ```

不要使用 `down -v` 删除旧卷，也不要让两个实例同时访问它。外部卷必须已经存在；Compose 不会创建或删除它。若第一步没有输出卷名，说明可能使用了宿主机目录挂载，需要按实际路径配置 bind mount，不能将路径填入 `DATA_VOLUME`。

Do not delete the old volume with `down -v`, and do not run two instances against it. An external volume must already exist; Compose will not create or remove it. If inspection returns no volume name, inspect the mounts for a host bind directory and configure that bind mount explicitly instead of using its path as a volume name.

## Container and proxy settings

The container listens on `0.0.0.0:7000`. Host publication is controlled by `BIND_ADDRESS` and `PORT` in Compose. Authentication is based on `PUBLISHED_BIND_ADDRESS`; when this variable is absent, authentication is required. The default remote password remains `pdf2zh`.

Keep the UI and API on one origin. Disable proxy buffering for `/events` and allow long-lived connections. For HTTPS access, set `COOKIE_SECURE=true`.

Only one instance may own a data volume. All source PDFs, results, document caches, and job logs belong to per-job directories under `/data/tasks`. Public engine assets are stored in the image. Model profiles and access-session configuration live under `/data/config`.
