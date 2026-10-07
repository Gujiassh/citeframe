# 本地环境 profile：preview 与 accept

## 选择运行 profile

| Profile | 用途 | 生成 | Embedding |
|---|---|---|---|
| **preview** | 产品预览与日常问答 | 配置的 OpenAI-compatible 服务 | 本地 Ollama（默认） |
| **accept** | 自动化检查 | 确定性测试响应 | 确定性测试向量 |

日常问答使用 **preview**。**accept** 提供固定响应，用于检查接口、状态和处理链路；这些响应不能用于判断模型质量。

`infra/scripts/citeframe-local-env.sh` 会拒绝 preview 使用测试 generation endpoint。
检查脚本应使用 accept profile 或独立环境，结束后执行 `stop`，保留 preview 的模型配置。

## 配置模型密钥

- `infra/env/preview.env.example` 不包含模型 API key。
- 复制为 `preview.local.env` 后自行填写 `AI_PDF_OPENAI_API_KEY`（或 `OPENAI_API_KEY`）。本地密钥文件已加入 gitignore。
- 缺少 generation key 时仍可启动基础服务；依赖生成、caption 或 ASR 的路径返回明确配置错误，例如 `image_caption_provider_not_configured` / `asr_not_configured`。
- Embedding 默认走本机 Ollama，地址为 `http://127.0.0.1:11434`；需自行运行 `ollama pull qwen3-embedding:0.6b`。

## 文件

| 路径 | 说明 |
|---|---|
| `infra/env/preview.env.example` | preview 模板（无密钥；embed → 11434） |
| `infra/env/accept.env.example` | accept 模板（全 stub） |
| `infra/env/preview.local.env` | 本机密钥与覆盖（gitignored，自行创建） |
| `infra/env/accept.local.env` | 本机 accept 覆盖（gitignored） |
| `infra/scripts/citeframe-local-env.sh` | 切换 / 启停 / 状态 |

## 用法

```bash
cp infra/env/preview.env.example infra/env/preview.local.env
# 可选：在 preview.local.env 写入 AI_PDF_OPENAI_API_KEY=... 

docker compose -f infra/docker/compose.yml up -d
# 本机 Ollama 需可用（embedding）
# ollama serve && ollama pull qwen3-embedding:0.6b

infra/scripts/citeframe-local-env.sh preview start
infra/scripts/citeframe-local-env.sh preview start --with-web

infra/scripts/citeframe-local-env.sh accept start

infra/scripts/citeframe-local-env.sh preview status
infra/scripts/citeframe-local-env.sh preview stop
```

## 过渡：仅当你的库仍是 stub 向量时

若历史数据是 **accept stub 灌的向量**，立刻改到 `11434` 可能触发 embedding index / fingerprint fail-closed。

需要临时兼容旧索引时，将覆盖写在 `preview.local.env`；完成重建后移除。example 保持真实 Ollama 默认配置：

```bash
# transitional only — reindex ASAP then remove
AI_PDF_OLLAMA_BASE_URL=http://127.0.0.1:18081
```

脚本在 preview 下若发现 ollama 指向 18081，会 **只为 embedding 拉起 stub** 并打印警告，但仍 **拒绝** 把 generation base 设为 18081。

长期：用真 embedding reindex 后，保持 `AI_PDF_OLLAMA_BASE_URL=http://127.0.0.1:11434`。

## Web

BFF 读取 `apps/web/.env.local`。先从 `apps/web/.env.example` 复制，至少配置：

- `AI_PDF_API_BASE_URL=http://127.0.0.1:8000`；
- 与 API 完全一致的 `AI_PDF_API_INTERNAL_TOKEN`；
- 独立且不可提交的 `AI_PDF_SESSION_SECRET`，用于 httpOnly session cookie 签名。

profile 主要切换 **API/Worker 后端**，但 Web 的 internal token 必须与所选 profile
一致。缺少 `AI_PDF_SESSION_SECRET` 时注册 API 仍可成功，登录 BFF 会明确 fail closed，
不会创建未签名 session。

## 自动化检查

检查脚本使用隔离 Compose 或 accept profile，保留 `preview.local.env` 中的模型配置。

## 数据库迁移与 ASR / vision 配置

将本地 Postgres 迁移到 Alembic head，以加载包含 Office/HTML/Audio/Video 的 `asset_types` 目录：

```bash
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
uv run --project apps/api alembic -c apps/api/alembic.ini current
```

### Vision caption + ASR (preview)

Both use the **same OpenAI-compatible secret** (`AI_PDF_OPENAI_API_KEY` / `OPENAI_API_KEY`)
and base (`AI_PDF_OPENAI_API_BASE`, preview template default `http://127.0.0.1:8317/v1`).

| Capability | Settings | Fail-closed code when missing |
| --- | --- | --- |
| Chat / generation | `AI_PDF_GENERATION_PROVIDER` + OpenAI-compatible key | `generation_provider_not_configured` |
| Image / PDF abstract caption | `AI_PDF_IMAGE_CAPTION_PROVIDER=openai`, `AI_PDF_IMAGE_CAPTION_MODEL=gpt-5.5` | `image_caption_provider_not_configured` |
| Audio/Video transcript | `AI_PDF_ASR_PROVIDER=openai`, `AI_PDF_ASR_MODEL=whisper-1` | `asr_not_configured` |

Put secrets in `apps/api/.env`, `apps/worker/.env`, and/or `infra/env/preview.local.env`
(gitignored). API and Worker must see the **same** key + base when you want those paths live.

The configured OpenAI-compatible service must be available for preview generation/caption/ASR. `curl` to `/v1/models`
may return 401 without a key; capability readiness only checks **key configured**,
not live model list.

Ollama is for **embedding** by default. Do not use the acceptance stub for product preview.
