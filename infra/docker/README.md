# Docker

本目录提供两套互不覆盖的 Compose 配置：

- `compose.yml`：只启动本地开发依赖，Web、API 和 Worker 仍在宿主机运行。
- `compose.deploy.yml`：构建并启动完整单机部署，使用独立具名卷保存数据。

## 启动本地开发依赖

运行：

```bash
docker-compose -f infra/docker/compose.yml up -d
cd apps/api
uv run alembic upgrade head
```

本地 Compose 默认 PostgreSQL 暴露 `127.0.0.1:5432`，MinIO API/console 暴露 `127.0.0.1:9010/9011`，避免与本机其他 MinIO 服务占用的 `9000/9001` 冲突。PostgreSQL 和 MinIO 使用 `restart: unless-stopped`；若服务被手动停止，使用下面的 `up -d` 恢复。

Postgres 使用 `pgvector/pgvector:pg17`。Alembic 会启用 `vector` 和 `pg_trgm` 扩展，并创建 `vector(1024)` HNSW、lexical FTS GIN、中文 trigram GiST 索引及业务真表。

PostgreSQL 数据保存在 Compose named volume `docker_postgres_data`，MinIO 数据保存在 `infra/docker/data/minio` bind path；不要把 SolarSense 的 `9000/9001` endpoint 填入 Citeframe API/Worker env。

本地 Ollama 不由 Compose 管理。需要本地 embedding 时，确保 `http://127.0.0.1:11434` 提供 `qwen3-embedding:0.6b`，并让 API 与 Worker 使用相同的 provider、model 和 version。

## 准备完整部署配置

从仓库根目录运行：

```bash
cp infra/docker/.env.deploy.example infra/docker/.env.deploy
```

编辑 `infra/docker/.env.deploy`，至少替换以下值：

- `POSTGRES_PASSWORD`
- `MINIO_ROOT_USER` 和 `MINIO_ROOT_PASSWORD`
- `AI_PDF_API_INTERNAL_TOKEN`
- `AI_PDF_SESSION_SECRET`
- `AI_PDF_OPENAI_API_KEY` 和需要的 API base URL
- `CADDY_SITE_ADDRESS`：生产环境使用真实域名，例如 `pdf.example.com`

`AI_PDF_API_IMAGE`、`AI_PDF_WORKER_IMAGE` 和 `AI_PDF_WEB_IMAGE` 默认使用本机构建标签。CI/CD 推送镜像后，将它们改为带不可变版本或 digest 的镜像地址；migration 与 API 必须使用同一个 API 镜像。Dockerfile 基础镜像以及 Compose 的 Postgres、Redis、MinIO、Caddy 均固定到已验证 digest。

`POSTGRES_DB`、`POSTGRES_USER`、`MINIO_ROOT_USER`、`MINIO_ROOT_PASSWORD` 和 `MINIO_BUCKET` 同时被 Compose 与备份脚本读取，必须使用不含空格、引号或 `#` 的单行值；`POSTGRES_PASSWORD` 还应使用 URL-safe 字符。环境文件已被仓库忽略，不要提交真实密钥。

默认 embedding provider 是宿主机 Ollama。Linux Compose 通过 `host.docker.internal:host-gateway` 将容器请求转到宿主机；如果使用独立模型服务，修改 `AI_PDF_OLLAMA_BASE_URL`。

检索默认使用 `hybrid`、`candidate_k=10` 和 `RRF=60`。Dense-only 回归必须显式设置 `AI_PDF_RETRIEVAL_STRATEGY=dense`；服务不会在 Hybrid 错误时静默降级。

## 校验并启动完整部署

先检查变量替换和服务依赖：

```bash
docker-compose \
  --env-file infra/docker/.env.deploy \
  -f infra/docker/compose.deploy.yml \
  config
```

然后构建并启动：

```bash
docker-compose \
  --env-file infra/docker/.env.deploy \
  -f infra/docker/compose.deploy.yml \
  up -d --build
```

启动顺序固定为：

1. Postgres 和 MinIO 通过健康检查。
2. `migration` 执行 `alembic upgrade head` 并成功退出。
3. API 和 Worker 启动；API 通过 readiness。
4. Web 启动并通过健康检查。
5. Caddy 启动，成为唯一公开应用入口。

Redis 同时启动并持久化 AOF，但当前业务主链仍使用 Postgres 任务表；它不会参与 migration gate。

## 检查运行状态和日志

查看状态：

```bash
docker-compose \
  --env-file infra/docker/.env.deploy \
  -f infra/docker/compose.deploy.yml \
  ps
```

查看 migration、API 和 Worker 日志：

```bash
docker-compose \
  --env-file infra/docker/.env.deploy \
  -f infra/docker/compose.deploy.yml \
  logs migration api worker
```

生产浏览器只访问 `https://${CADDY_SITE_ADDRESS}`。Caddy 自动申请/续期证书并返回 HSTS、`nosniff`、frame deny 和 referrer policy。Web、API、Worker、Postgres、Redis 和 MinIO API 不发布到宿主机；MinIO console 只绑定 `127.0.0.1:${MINIO_CONSOLE_PORT:-9001}`。

本地入口 smoke 不伪造 TLS。使用单独的 smoke env 值：

```bash
CADDY_SITE_ADDRESS=http://:80
CADDY_HTTP_PORT=3000
CADDY_HTTPS_PORT=3443
```

然后访问 `http://127.0.0.1:3000`。

API 探针：

- `/health/live` 只判断 API 进程是否存活。
- `/health/ready` 检查数据库、对象存储、embedding provider 和 generation provider。

Web BFF 与 API 必须共享 `AI_PDF_API_INTERNAL_TOKEN`。该 token 只存在于服务端环境变量，浏览器不携带。

## 指标

API `/metrics` 和 Worker `9101` 只在 Compose 私网开放，不由 Caddy 代理。可从容器内检查：

```bash
docker-compose --env-file infra/docker/.env.deploy -f infra/docker/compose.deploy.yml \
  exec -T api python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/metrics').read().decode())"

docker-compose --env-file infra/docker/.env.deploy -f infra/docker/compose.deploy.yml \
  exec -T api python -c \
  "import urllib.request; print(urllib.request.urlopen('http://worker:9101/metrics').read().decode())"
```

指标覆盖 HTTP、provider、Dense/Hybrid retrieval、MinIO、ingestion job 和 Worker job/active。label 不包含问题、正文、文档名、UUID path 或对象 key。

## 备份与恢复

必须显式传部署 env、Compose project 和新的输出目录：

```bash
infra/scripts/backup-deployment.sh \
  --env-file infra/docker/.env.deploy \
  --project ai-pdf-production \
  --output-dir /srv/backups/ai-pdf/2026-07-16T120000Z
```

备份会在同一窗口停止 Caddy、Web、API 和 Worker，生成 PostgreSQL custom dump、MinIO mirror、绑定 project/database/bucket 的 manifest 和闭集 `SHA256SUMS`，完成后重启服务。输出目录权限为 700，文件为 600。

脚本默认固定到已验证的 `minio/mc` release digest，避免备份/恢复工具随 tag 漂移。离线部署需要提前拉取该镜像。

恢复是破坏性运维动作，只允许恢复到同名 project 的空数据库、空 Redis 和空 bucket：

```bash
infra/scripts/restore-deployment.sh \
  --env-file infra/docker/.env.deploy \
  --project ai-pdf-production \
  --backup-dir /srv/backups/ai-pdf/2026-07-16T120000Z \
  --confirm
```

恢复在启动应用前完成以下检查：

- manifest 版本、project、database 和 bucket 必须匹配
- checksum 清单必须与文件闭集完全一致，拒绝 symlink、特殊文件、重复和越界路径
- PostgreSQL custom archive 必须可列出
- 目标数据库不得存在用户 schema 对象，Redis 必须为零 key，目标 bucket 必须为空
- MinIO list/find、权限或网络失败会在 PostgreSQL 和对象回放前中断，不能当作空 bucket
- PostgreSQL 使用单事务恢复，MinIO 恢复后回读并逐文件比较
- Alembic 重跑成功后才启动 API、Worker、Web 和 Caddy；所有长期服务达到 healthy/running 后才报告完成

恢复中途失败不会打印 `restore_complete`。清理失败的空/部分恢复目标后，从原备份重新开始；不要对非空环境续跑或覆盖。

## 重跑迁移和停止服务

Alembic upgrade 可重复执行。需要手动重跑时：

```bash
docker-compose \
  --env-file infra/docker/.env.deploy \
  -f infra/docker/compose.deploy.yml \
  run --rm migration
```

停止容器但保留数据卷：

```bash
docker-compose \
  --env-file infra/docker/.env.deploy \
  -f infra/docker/compose.deploy.yml \
  down
```

不要对需要保留的数据运行 `down -v`。只有在已验证备份且明确执行空环境恢复演练时，才销毁指定 Compose project 的卷。

本机 Docker 29 与旧 `docker-compose 1.29.2` 的 recreate 路径可能出现 `ContainerConfig` 错误；生产环境优先使用 Compose v2。旧 v1 环境需要变更服务容器配置时，应先停止并删除对应应用容器，再重新 `up`，不能删除数据卷。
