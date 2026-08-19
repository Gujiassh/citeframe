# Citeframe 当前执行计划（整理版）

Date: 2026-08-18
Status: **current execution SSOT**（工程主线已关闭，当前仅维护 residual execution）
Product stage: `internal_preview`

本文是唯一当前执行入口。V5-F、architecture-hardening 和 PPTX layout/embed preview 已在 main 关闭；旧的 W1/PDF-Visual 并行计划只保留为历史记录，不代表仍在开发。当前只维护 ops 真复配与 V5-E 后置证据的状态、owner、阻塞条件和下一步。
更细的字段合同仍以下游文档为准；冲突时以本文当前状态和已批准 decision 为准。

---

## 1. 当前目标与边界

工程主线已经收口。当前目标不是继续开启 W1 功能开发，而是为 `internal_preview` 补齐发布前证据和运行环境证据：

1. **Ops 真复配**：在环境就绪时完成真实 Ollama reindex、preview 真 key 冒烟和多 provider live E2E。
2. **V5-E 后置证据**：取得明确授权后，以新目录运行 R803 真模型质量评估，并完成 M404 用户价值协议、执行和发布判断。
3. **Residual 记录**：任何失败、阻塞或环境缺失都写入本入口，不以“工程门通过”替代模型质量或用户价值结论。

**不做**：在没有独立决策包的情况下重开动态 Agent DAG、`ai_pdf_*` 重命名、新模态或更强 mixed Research seed。Office/PPT 深度 WYSIWYG 继续作为已知产品限制。

---

## 2. 历史决策与当前状态

本节保留 2026-08-13 的 O1-O5 决策记录，作为已关闭 V5-F 的追溯材料；它们不再构成新的开工门。

### 2.1 已拍板（历史决策，执行已完成）

| ID | 内容 |
|---|---|
| D1 | V5-F 范围：补全 HTML/Office/Audio/Video + 跨模态 Agent 完善 |
| D2 | 多模态 **分线并行** 收尾，P0 优先于付费评测 |
| D3 | Agent 仍是 **固定 DAG**，不做动态图/自由插件 |
| D4 | 付费 formal R803 **暂缓** |
| D5 | 本地 **preview / accept 环境分型**；日常生成走 **本机 CLIProxy**，不直连 SourcesData |
| D6 | 图片/区域视觉默认模型：**gpt-5.5**（与 generation 同 profile，经 CLIProxy） |

### 2.2 主人拍板记录（2026-08-13）

| ID | 问题 | 决定 |
|---|---|---|
| **O1** | PDF 页内视觉优先级 | **按推荐：与 W1 并行，P0'** |
| **O2** | 抽象图 v1 | **必须上 gpt-5.5 caption**（不能只 OCR） |
| **O3** | Office kinds | **按推荐：docx / xlsx / pptx 三个 kind** |
| **O4** | embedding 脱离 stub | **按推荐：不挡 W1，中后期 reindex** |
| **O5** | 是否开工 | **已开工**（2026-08-13 主人：清仓提交后按车道双人制推进） |

### 2.3 「accept 才用 stub」是什么意思

本机有两种跑法，**stub = 假模型服务**（`provider_m403b_stub.py`，端口 `18081`）：

| 名字 | 干什么 | 生成（问答/写描述） | 向量（检索用 embedding） |
|---|---|---|---|
| **preview** | 你日常打开 3100 用产品 | **真模型**，经本机 **CLIProxy :8317**（gpt-5.5） | 默认真 Ollama；既有 stub 向量需显式 reindex |
| **accept** | 跑 M403B/混合等**工程验收** | **整段假模型**（固定英文、不烧钱、可重复） | **也用假 embedding** |

所以：

- **「accept 才用 stub」** = 只有做**自动化验收/灌证据**时，才允许 generation 指到 `18081` 假服务。  
- **日常预览/问答** = preview，**禁止** generation 走 stub（否则又会看到 Image 固定英文）。  
- 验收脚本应 `accept start`，验收完 `stop`，不要把日常 API 长期留在 accept。

stub 的固定回答 **不是** 模型质量，只证明管道通。


---

## 3. 工作流全景（当前）

```text
已关闭（工程）
  V1–V4 · V5-A/B/C/D/F · architecture-hardening · PPTX layout/embed preview

当前 residual execution
  OPS：真实 Ollama reindex · preview 真 key 冒烟 · 多 provider live E2E
  V5-E：R803 真模型质量 · M404 用户价值 · Beta/公开发布判断

明确后置/不在当前主线
  动态 Research DAG · ai_pdf_* 重命名 · 新模态 · 更强 mixed Research seed
```

preview/accept 的环境分型仍有效，但它是运行约束，不是 W1 的开工状态。


### 3.1 Residual execution board（唯一 active residual）

| ID | 当前状态 | 前置条件 | 完成证据 |
|---|---|---|---|
| OPS-1 | `pending_environment` | 可用的 Ollama、preview 真 key 和目标 provider profile；指定 owner | reindex 命令/日志、索引合同核验、preview smoke 和多 provider live E2E artifact |
| V5-E-R803 | `deferred_authorization` / `not_evaluable` | owner 明确批准预算、provider/profile 和全新 campaign 目录 | 新 campaign 的完整 round/report/hash；冻结 v1 不恢复、不覆盖 |
| V5-E-M404 | `blocked_input` / `not_evaluable` | 批准协议、目标用户和合格任务样本 | M404 原始记录、资格判定和用户价值报告 |

**派生门禁（不是独立 residual）**：Release review / Beta / 公开发布判断只在 OPS-1、R803、M404 证据齐备后派生裁决；不得单独写成当前可执行项。

**非 active residual**：mixed Research seed、动态 Research DAG、`ai_pdf_*` 重命名、新模态、Office/PPT 深度 WYSIWYG 属于产品债或独立决策包，不进入本 board。

下一步只做两类选择：为 OPS-1 指定环境和 owner，或为 V5-E 明确授权/输入。未满足前置条件时保留当前状态，不虚构进行中。

---

## 4. 历史执行波次（已关闭）

以下 W0-W3/PDF-Visual 内容保留为实施记录；V5-F 和 PV-0..PV-5 已完成，不能据此判断当前仍在 W1。

### 主线 A — V5-F 模态分线收尾

权威细节：[`parallel-execution-plan-v5f.md`](parallel-execution-plan-v5f.md)、[`v5f-detailed-spec.md`](v5f-detailed-spec.md)

| Wave | 并行内容 | 出口 |
|---|---|---|
| **W0** | 开工检查；S0 共享合入队列；HTML sanitizer 政策成文 | 可开 W1 |
| **W1** | HTML ∥ DOCX ∥ XLSX ∥ PPTX ∥ ASR ∥ AGENT(文档类) | 各 F-G-* |
| **W2** | Audio ∥ Video（ASR 已绿）∥ AGENT 扩展 | 音视频闭环 |
| **W3** | 全模态 MIX restore + 全量 Critical | V5-F engineering 收尾 |

共享内核 **S0 串行**（registry / catalog / OpenAPI union / retrieval）。

### 主线 B — PDF 页内视觉 v1（P0'）

**问题**：没有内嵌 Image XObject 的 PDF，页上截图/抽象图识别不到。

| 步 | 内容 | 带字截图 | 抽象图 |
|---|---|---|---|
| B1 | 页面渲染 + 图块候选（不依赖 get_image_info） | 框到 | 框到 |
| B2 | 区域 OCR → 可检索 ContentUnit + pdf_region | 能搜字 | 可能字少 |
| B3 | 区域 caption（**gpt-5.5** / 现有 vision capability） | 增强 | **必需** |
| B4 | 问答命中 region 时把裁切图塞进 generation | 完整 | 完整 |

验收一句话：

> 无内嵌图 PDF：带字截图能搜到字并高亮；抽象图能框到区域，问答能引用 region 且用到图意。

合同：仍挂 PDF Asset，不拆成独立 Image Asset。  
规格落点：[`pdf-in-page-visual-v1.md`](pdf-in-page-visual-v1.md)（本包新建）。

### 两条主线关系

- **可并行**：PDF-Visual 改 Worker PDF 管道；V5-F HTML/Office 改各自 adapter。  
- **冲突点**：`retrieval` / OpenAPI locator union / citation 展示 → 走 **S0**。  
- Agent 线：文档类先吃 HTML/Office；PDF region 视觉就绪后立刻吃 pdf_region 带图。

---

## 5. Vision / 模型用法（冻结）

| 用途 | 模型 | 接入 |
|---|---|---|
| 区域/图片 caption | **gpt-5.5** | 现有 `vision` / `image_caption` |
| 问答带图 | **gpt-5.5** | 现有 `generation` 多模态 |
| 图上的字 | RapidOCR（区域） | 现有 OCR 路径扩展 |
| 本地 endpoint | **CLIProxy** `http://127.0.0.1:8317/v1` | preview profile |

禁止：preview 的 generation 指向 M403B stub `:18081`。  
preview embedding 默认走真 Ollama；accept 才使用 18081 stub。既有 stub 向量迁移和 reindex 证据属于 OPS-1。

---

## 6. 本地环境

| Profile | 用途 | 生成 | Embedding |
|---|---|---|---|
| **preview** | 日常 3100 | CLIProxy + gpt-5.5 | 真 Ollama（默认；既有 stub 索引需 reindex） |
| **accept** | 工程验收 only | stub 18081 | stub 18081 |

文档：[`docs/architecture/local-env-profiles.md`](../../../docs/architecture/local-env-profiles.md)  
脚本：`infra/scripts/citeframe-local-env.sh`

---

## 7. 明确不做 / 后置

| 项 | 态度 |
|---|---|
| 动态 Agent / 自由工具 / 通用平台 | 不做 |
| Provider 选择器 UI | 不做 |
| 付费 R803 formal | 暂缓 |
| M404 | 后置 |
| 工程绿 = 模型质量 | 禁止宣称 |

---

## 8. 文档地图（读什么）

| 文档 | 角色 |
|---|---|
| **本文** `current-execution-plan.md` | **唯一当前执行 SSOT（2026-08-18）** |
| `decision-2026-08-13-v5f-scope.md` | V5-F 范围批准 |
| `parallel-execution-plan-v5f.md` | 模态并行线卡与 S0 |
| `v5f-detailed-spec.md` | 模态字段级合同 |
| `pdf-in-page-visual-v1.md` | PDF 页内视觉合同 |
| `verification-matrix-v5f.md` | 模态验收门 |
| `plan-audit-v5f.md` | 原 V5-F 审计 |
| `docs/architecture/local-env-profiles.md` | preview/accept |
| `docs/architecture/implementation-progress.md` | 进度日志 |

---

## 8.1 合作模式

开发协作按 [`collaboration-mode-lane-pairs.md`](collaboration-mode-lane-pairs.md)：**主控分波次；每线一工作区 + 开发/审计；MR 由主控终审合入后删分支。** 先手动，不先做调度工具。

## 9. 历史开工检查单（已完成/不再作为当前门）

以下原始清单按 2026-08-13 快照保留；未勾选不代表当前阻塞，当前不得重新据此启动 W1：

- [ ] 主人确认 O1–O4 或接受推荐默认
- [ ] 主人明确「开工」
- [ ] `preview status`：CLIProxy 生成、非 SourcesData、非 generation→18081
- [ ] S0 owner 指定
- [ ] 第一波并行集合确认：默认 `PDF-Visual + HTML + DOCX + XLSX + PPTX + ASR + AGENT`
- [ ] git 身份/远程检查（仓库规则）

---

## 10. 当前状态（2026-08-18）

| 项 | 状态 |
|---|---|
| 当前入口 | **本文；其他计划只作历史/字段合同** |
| V5-F / architecture-hardening / PPTX layout | **工程已关闭（main）** |
| 产品阶段 | **`internal_preview`** |
| W1 / PDF-Visual | **已完成；无当前实现任务** |
| Ops 真复配（OPS-1） | **active residual：等待环境/owner 证据** |
| R803 真实模型质量 | **active residual：`not_evaluable`；需明确授权后新 campaign** |
| M404 用户价值 | **active residual：`not_evaluable`；需协议、目标用户和执行证据** |
| Release review | **派生门禁，非独立 residual** |
| 下一动作 | **先选定 OPS 或 V5-E owner，记录命令/环境/artifact；完成后回写本表** |
