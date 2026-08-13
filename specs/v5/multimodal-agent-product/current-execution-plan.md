# Citeframe 当前执行计划（整理版）

Date: 2026-08-13  
Status: **active planning SSOT**（实现仍待主人开工令）  
Product stage: `internal_preview`

本文把已批准范围、并行编组、PDF 页内视觉、vision 用法、本地环境分型收成**一份当前主计划**。  
更细的字段合同仍以下游文档为准；冲突时以本文「优先级与波次」+ 已批准 decision 为准。

---

## 1. 一句话目标

把 Citeframe 从「PDF/图/Markdown 很深、其它模态半吊子」收成：

1. **多模态能力面补全**（HTML / Office / Audio / Video 纵向闭环）  
2. **PDF 页内图也能认**（无内嵌图 + 抽象图）  
3. **固定 DAG Research 吃得下全部已启用模态**  
4. **本地 preview 用真生成（CLIProxy），accept 用 stub**  

**不做**：通用 Agent 平台、用户 provider 选择器、把工程绿当模型质量。  
**后置**：付费 R803 formal、M404 用户价值。

---

## 2. 已拍板 vs 待拍板

### 2.1 已拍板（主人已确认）

| ID | 内容 |
|---|---|
| D1 | V5-F 范围：补全 HTML/Office/Audio/Video + 跨模态 Agent 完善 |
| D2 | 多模态 **分线并行** 收尾，P0 优先于付费评测 |
| D3 | Agent 仍是 **固定 DAG**，不做动态图/自由插件 |
| D4 | 付费 formal R803 **暂缓** |
| D5 | 本地 **preview / accept 环境分型**；日常生成走 **本机 CLIProxy**，不直连 SourcesData |
| D6 | 图片/区域视觉默认模型：**gpt-5.5**（与 generation 同 profile，经 CLIProxy） |

### 2.2 主人拍板记录（2026-08-13）
### 2.3 「accept 才用 stub」是什么意思

本机有两种跑法，**stub = 假模型服务**（`provider_m403b_stub.py`，端口 `18081`）：

| 名字 | 干什么 | 生成（问答/写描述） | 向量（检索用 embedding） |
|---|---|---|---|
| **preview** | 你日常打开 3100 用产品 | **真模型**，经本机 **CLIProxy :8317**（gpt-5.5） | 过渡期可仍用 18081；以后 reindex 换真 Ollama |
| **accept** | 跑 M403B/混合等**工程验收** | **整段假模型**（固定英文、不烧钱、可重复） | **也用假 embedding** |

所以：

- **「accept 才用 stub」** = 只有做**自动化验收/灌证据**时，才允许 generation 指到 `18081` 假服务。  
- **日常预览/问答** = preview，**禁止** generation 走 stub（否则又会看到 Image 固定英文）。  
- 验收脚本应 `accept start`，验收完 `stop`，不要把日常 API 长期留在 accept。

stub 的固定回答 **不是** 模型质量，只证明管道通。



| ID | 问题 | 决定 |
|---|---|---|
| **O1** | PDF 页内视觉优先级 | **按推荐：与 W1 并行，P0'** |
| **O2** | 抽象图 v1 | **必须上 gpt-5.5 caption**（不能只 OCR） |
| **O3** | Office kinds | **按推荐：docx / xlsx / pptx 三个 kind** |
| **O4** | embedding 脱离 stub | **按推荐：不挡 W1，中后期 reindex** |
| **O5** | 是否开工 | **已开工**（2026-08-13 主人：清仓提交后按车道双人制推进） |

---

## 3. 工作流全景（当前）

```text
已完成（工程）
  V1–V4 基线 · V5-A Provider · V5-B Markdown · V5-C 固定多 Agent
  V5-D 混合整合门 · D-G6/D-G7 · 本地 env 分型

进行中（计划层）
  V5-F 模态并行收尾
  PDF 页内视觉 v1（无内嵌图 + 抽象图）
  preview=CLIProxy/gpt-5.5

后置
  付费 R803 · M404 · Beta 判断
```

---

## 4. P0 双主线

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
Embedding 过渡期可仍用 18081，见环境文档。

---

## 6. 本地环境

| Profile | 用途 | 生成 | Embedding |
|---|---|---|---|
| **preview** | 日常 3100 | CLIProxy + gpt-5.5 | 过渡 stub 或真 Ollama |
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
| **本文** `current-execution-plan.md` | **当前执行 SSOT** |
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

## 9. 开工检查单（O5 通过后）

- [ ] 主人确认 O1–O4 或接受推荐默认  
- [ ] 主人明确「开工」  
- [ ] `preview status`：CLIProxy 生成、非 SourcesData、非 generation→18081  
- [ ] S0 owner 指定  
- [ ] 第一波并行集合确认：默认 `PDF-Visual + HTML + DOCX + XLSX + PPTX + ASR + AGENT`  
- [ ] git 身份/远程检查（仓库规则）

---

## 10. 状态（2026-08-13）

| 项 | 状态 |
|---|---|
| 计划整理 | **done** |
| O1–O4 | **已拍板**（见 §2.2） |
| O5 开工 | **是** |
| 实现 | **W1 启动中**（lane pairs） |
| 本地 preview 生成 | CLIProxy + gpt-5.5 |
| 下一动作 | 分工作区：PDF-Visual / HTML / Office / ASR；每线开发+审计 → MR → 主控合入 |
