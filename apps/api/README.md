# API App

FastAPI 业务后端入口。

当前状态：
- 提供 `/health`、`/health/live`、`/health/ready`、`/v1/auth/*`、`/v1/workspaces*`、documents/ingestion、threads/messages、chat stream、notes/tags CRUD 与 document/note tag bindings 链路
- 业务 API 只接受 BFF 注入的 `x-user-id` + `x-ai-pdf-internal-token`；登录/注册和健康检查保持公开
- Workspace 的系统提示词、检索 top-k、入库 chunk size 已落真实表并由 `/v1/workspaces/{workspace_id}/settings` 持久化
- 数据库结构现在通过显式版本步骤管理，不再依赖应用启动时自动建表；当前 head 为 `a3c5e7f9b1d4`，该版本启用 `asset_types.image` 目录，不改变 API payload 或保存语义

## 本地常用命令

初始化或升级本地数据库结构：

```bash
cd apps/api
uv run alembic upgrade head
```

如果你的本地库是在接入数据库版本步骤之前就已经用旧方式自动建好的，而且当前表结构已经与代码一致，可以只打版本标记而不重建表：

```bash
cd apps/api
uv run alembic stamp head
```

新增下一版数据库结构变更草稿：

```bash
cd apps/api
uv run alembic revision --autogenerate -m "描述这次改表做了什么"
```

运行后端测试：

```bash
cd /home/cc/code/citeframe
uv run --project apps/api pytest apps/api/tests
```


## 模型运行时配置

API 和 Worker 共享 embedding 配置。当前本地回归使用 Ollama：

```bash
export AI_PDF_API_INTERNAL_TOKEN=replace-with-a-shared-internal-token
export AI_PDF_EMBEDDING_PROVIDER=ollama
export AI_PDF_EMBEDDING_MODEL=qwen3-embedding:0.6b
```

这个模型返回 1024 维向量，对应数据库里的 `vector(1024)`。如果使用支持 Embeddings API 的 OpenAI 账号，可以改成：

```bash
export AI_PDF_EMBEDDING_PROVIDER=openai
export AI_PDF_EMBEDDING_MODEL=text-embedding-3-small
export OPENAI_API_KEY=...
export OPENAI_API_BASE=https://api.openai.com/v1
```

`OPENAI_API_BASE` 可以填写网关根地址，代码会自动补 `/v1`。当前项目的 OpenAI 网关如果不提供 embedding 模型，必须使用 Ollama 或换成支持 embedding 的账号/网关；不会自动把失败请求伪装成可用结果。

Chat generation 当前支持 OpenAI Responses API 和 DeepSeek Anthropic Messages API。切换到 DeepSeek 时：

```bash
export AI_PDF_GENERATION_PROVIDER=deepseek
export AI_PDF_GENERATION_MODEL=deepseek-v4-pro
export AI_PDF_DEEPSEEK_API_KEY=...
export AI_PDF_DEEPSEEK_API_BASE=https://api.deepseek.com/anthropic
```

官方当前 `/models` 返回 `deepseek-v4-flash` 与 `deepseek-v4-pro`；适配器会把 base 规范化到 `/anthropic/v1/messages`。这只证明 provider 接入和工程链路可用，不代表模型质量评估已完成。API 与 Worker 还必须共享同一个数据库、MinIO endpoint 和 embedding provider/model/version 配置；本机 MinIO 若不是 Compose 默认的 `127.0.0.1:9000`，请同时设置 `AI_PDF_MINIO_ENDPOINT`。

数据库升级：

```bash
cd apps/api
uv run alembic upgrade head
```

## 运行边界

- `AI_PDF_API_INTERNAL_TOKEN` 必须和 Web BFF 使用同一个值；生产环境不要使用代码内置的本地开发默认值。
- `AI_PDF_CAPABILITY_FINGERPRINT_PEPPER` 是 capability profile 指纹的独立 server-side pepper；API 与 Worker 必须一致。它只参与 secret 的单向 marker，不会写入 profile/API/log；不要把它和 API key 或 internal token 混用。
- `/health` 和 `/health/live` 只表示进程存活；部署探针使用 `/health/ready`，它会检查数据库、对象存储、embedding provider 和 Chat generation 配置；生产 registry 启用 Image 时还会检查 caption provider/model/version 与共享 OpenAI 配置，但不会为 readiness 发起 caption 请求。
- 上传请求由 API 按流读取到 `SpooledTemporaryFile`，超过 `AI_PDF_MAX_UPLOAD_BYTES`（默认 100 MB）或与 upload-session 的 `byteSize` 不一致会拒绝，避免整包常驻内存。
