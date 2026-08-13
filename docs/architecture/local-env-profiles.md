# 本地环境分型：preview vs accept

## 问题

以前 M403B / 混合验收为了确定性，把 **generation + embedding** 都指到本机 stub（`:18081`）。
验收结束后进程常还挂着，日常打开 3100 做 PDF 问答时，会继续打到 stub，出现固定英文：

> The uploaded image is available as frozen Evidence from the production Image path.

这不是 PDF 被错判成 Image，而是 **生成链路整段挂在了 Image 验收假服务上**。

## 两个 profile（必须分开）

| Profile | 用途 | 生成 | Embedding | 是否允许产品问答 |
|---|---|---|---|---|
| **preview** | 日常预览、自己验 PDF/产品 | **本机 CLIProxy** `http://127.0.0.1:8317/v1`（不要直连 SourcesData） | 真 Ollama 或（过渡）仍用 stub 向量端 | **是** |
| **accept** | M403B / 混合工程门 | **仅 stub `:18081`** | **仅 stub `:18081`** | **否**（工程证据 only） |

规则：

1. **preview 禁止** `AI_PDF_OPENAI_API_BASE` 指向 `18081`。
2. **accept 禁止** 当产品预览入口。
3. 验收脚本应使用 accept profile 或自带隔离 env，结束后 `stop`。
4. stub 固定回答 **不是** 模型质量证据。

## 文件

| 路径 | 说明 |
|---|---|
| `infra/env/preview.env.example` | preview 模板（无密钥） |
| `infra/env/accept.env.example` | accept 模板 |
| `infra/env/preview.local.env` | 本机密钥与覆盖（gitignored，自行创建） |
| `infra/env/accept.local.env` | 本机 accept 覆盖（gitignored） |
| `infra/scripts/citeframe-local-env.sh` | 切换 / 启停 / 状态 |

## 用法

```bash
cp infra/env/preview.env.example infra/env/preview.local.env
# 在 preview.local.env 写入 AI_PDF_OPENAI_API_KEY=... 或 export OPENAI_API_KEY

docker compose -f infra/docker/compose.yml up -d

infra/scripts/citeframe-local-env.sh preview start
infra/scripts/citeframe-local-env.sh preview start --with-web

infra/scripts/citeframe-local-env.sh accept start

infra/scripts/citeframe-local-env.sh preview status
infra/scripts/citeframe-local-env.sh preview stop
```

## 过渡：embedding 仍用 stub

若当前库里的向量是 **accept stub 灌的**，preview 若立刻改成 `11434` 真 Ollama，可能触发 embedding index / fingerprint fail-closed。

过渡写法（写在 `preview.local.env`）：

```bash
AI_PDF_OPENAI_API_BASE=https://api.sourcesdata.com/v1
AI_PDF_OLLAMA_BASE_URL=http://127.0.0.1:18081
```

脚本在 preview 下若发现 ollama 指向 18081，会 **只为 embedding 拉起 stub**，但仍 **拒绝** 把 generation base 设为 18081。

长期：用真 embedding reindex 后，把 `AI_PDF_OLLAMA_BASE_URL` 改回 `11434`。

## Web

BFF 仍读 `apps/web/.env.local`（`AI_PDF_API_BASE_URL=http://127.0.0.1:8000`）。
profile 切换的是 **API/Worker 后端**，Web 一般不用换。

## 验收脚本

`run-m403*` / `run-v5d-mixed-*` 应继续用隔离 Compose 或 accept profile，
不要改写长期 `preview.local.env` 里的真 provider。

## S0 catalog migration + ASR / vision keys (2026-08-14)

After V5-F S0, local Postgres must be at Alembic head **`m7a8b9c0d1e2`** so
`asset_types` includes office/html/audio/video:

```bash
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
uv run --project apps/api alembic -c apps/api/alembic.ini current
# expect: m7a8b9c0d1e2 (head)
```

### Vision caption + ASR (preview)

Both use the **same OpenAI-compatible secret** (`AI_PDF_OPENAI_API_KEY` / `OPENAI_API_KEY`)
and base (`AI_PDF_OPENAI_API_BASE`, default CLIProxy `http://127.0.0.1:8317/v1`).

| Capability | Settings | Fail-closed code when missing |
| --- | --- | --- |
| Image / PDF abstract caption | `AI_PDF_IMAGE_CAPTION_PROVIDER=openai`, `AI_PDF_IMAGE_CAPTION_MODEL=gpt-5.5` | `image_caption_provider_not_configured` |
| Audio/Video transcript | `AI_PDF_ASR_PROVIDER=openai`, `AI_PDF_ASR_MODEL=whisper-1` | `asr_not_configured` |

Put secrets in `apps/api/.env`, `apps/worker/.env`, and/or `infra/env/preview.local.env`
(gitignored). API and Worker must see the **same** key + base.

CLIProxy must be up for preview generation/caption/ASR. `curl` to `/v1/models`
may return 401 without a key; capability readiness only checks **key configured**,
not live model list.

Ollama remains for **embedding** (or transitional stub), not for ASR/caption unless
a separate provider adapter is implemented later.

