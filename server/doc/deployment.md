# Deployment and data migration

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

4. 从新项目启动 / Start from the new project:

   ```sh
   docker compose up -d --build
   ```

不要使用 `down -v` 删除旧卷，也不要让两个实例同时访问它。外部卷必须已经存在；Compose 不会创建或删除它。若第一步没有输出卷名，说明可能使用了宿主机目录挂载，需要按实际路径配置 bind mount，不能将路径填入 `DATA_VOLUME`。

Do not delete the old volume with `down -v`, and do not run two instances against it. An external volume must already exist; Compose will not create or remove it. If inspection returns no volume name, inspect the mounts for a host bind directory and configure that bind mount explicitly instead of using its path as a volume name.

## Container and proxy settings

The container listens on `0.0.0.0:7000`. Host publication is controlled by `BIND_ADDRESS` and `PORT` in Compose. Authentication is based on `PUBLISHED_BIND_ADDRESS`; when this variable is absent, authentication is required. The default remote password remains `pdf2zh`.

Keep the UI and API on one origin. Disable proxy buffering for `/events` and allow long-lived connections. For HTTPS access, set `COOKIE_SECURE=true`.

Only one instance may own a data volume. All source PDFs, results, document caches, and job logs belong to per-job directories under `/data/tasks`. Public engine assets are stored in the image. Model profiles and access-session configuration live under `/data/config`.
