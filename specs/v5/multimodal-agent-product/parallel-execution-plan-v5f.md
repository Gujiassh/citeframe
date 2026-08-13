**上级当前执行 SSOT：** [`current-execution-plan.md`](current-execution-plan.md)

# V5-F 并行执行计划：多模态分线收尾

Date: 2026-08-13  
Status: **owner-aligned execution plan**（与主人确认：多模态拆多线并行、优先收尾）  
Depends on: [`decision-2026-08-13-v5f-scope.md`](decision-2026-08-13-v5f-scope.md)（已批准）、[`v5f-detailed-spec.md`](v5f-detailed-spec.md)、[`implementation-lanes-v5f.md`](implementation-lanes-v5f.md)、[`verification-matrix-v5f.md`](verification-matrix-v5f.md)、[`plan-audit-v5f.md`](plan-audit-v5f.md)

## 1. 一句话

**V5-F 是当前 P0。** 多模态按独立纵向闭环拆成多条并行线推进；共享内核单点串行；Agent 跨模态体验做伴随线；最后用全模态混合验收收口。  
**不**用通用 Agent 框架重做编排；**不**把付费 R803/M404 当作本阶段完成条件。

## 2. 目标与完成定义

### 2.1 要解决的问题

当前生产可用：`pdf`、`image`、Markdown `document`。  
HTML / Office / 音视频未形成同等闭环 → 产品能力面「半吊子」。

### 2.2 收尾完成（engineering）

同时满足：

1. 下列 kind 均已 registry enable，且各自具备完整纵向闭环（上传→解析→typed locator→检索→引用→Viewer→重试/删除/恢复）。
2. 混合 Workspace 可同时容纳全部已启用 kind，无跨 kind 泄漏。
3. 固定 DAG Research 能对全部已启用 kind 做 search/cite/open/recover（A1–A8，见 detailed-spec）。
4. 全模态混合 empty-target 备份恢复 + 全量回归 + Critical engineering ACCEPT。
5. 产品阶段仍可为 `internal_preview`；**不**宣称模型质量/用户价值通过。

### 2.3 每个模态的「完整」清单（门禁，不可降级）

| # | 项 |
|---|---|
| 1 | 声明 MIME + byte inspector，不匹配 fail-closed |
| 2 | 不可变 Representation + 类型化 ContentUnit |
| 3 | typed locator（禁止任意 JSON 当真） |
| 4 | 注册检索 channel；scope/generation/index 约束 |
| 5 | Citation / NoteSource 仅扩展 union，不改 envelope |
| 6 | Web Evidence 模块 + Viewer 高亮/定位 |
| 7 | retry / reprocess / delete 语义正确 |
| 8 | 备份/恢复含该 kind 对象与行身份 |
| 9 | focused 测试 + 至少一条生产路径证据 |
| 10 | Critical 或等价独立复审：`ACCEPT` 或 `ACCEPT with residuals` 后才 `enabled=true` |

缺任一项：该 kind **不得**对用户开放上传。

## 3. 并行编组（主图）

```text
P0 主线：V5-F 模态收尾（压过付费评测、压过炫 Agent）

┌─ 文档族并行 ─────────────────────────────────────┐
│  线 A  F-HTML     HTML（消毒/禁脚本政策先写死）     │
│  线 B  F-DOCX     Word                              │
│  线 C  F-XLSX     Excel                             │
│  线 D  F-PPTX     PowerPoint                        │
│  共享 S0  OpenAPI locator union / catalog / 检索签名 │
│           （主控或指定 shared owner 串行合入）        │
└──────────────────────────────────────────────────┘

┌─ 时序族 ─────────────────────────────────────────┐
│  线 E  F-ASR      ASR capability 合同 + fail-closed │
│         │                                         │
│         ├─→ 线 F  F-AUDIO   音频（等 E 绿）          │
│         └─→ 线 G  F-VIDEO   视频（等 E 绿；≠音频）   │
└──────────────────────────────────────────────────┘

┌─ 伴随线 ─────────────────────────────────────────┐
│  线 H  F-AGENT    跨模态 Evidence/Research UX      │
│                   文档族可先吃；全模态门等 F/G       │
│  线 P  F-PDF-VIS  PDF 页内视觉（无内嵌图/抽象图）   │
│                   可与文档族并行；见 pdf-in-page-visual-v1.md │
└──────────────────────────────────────────────────┘

┌─ 收口线（最后） ─────────────────────────────────┐
│  线 I  F-MIX      全启用 kind 混合 seed/restore     │
│  线 J  F-ACCEPT   全量回归 + Critical               │
└──────────────────────────────────────────────────┘
```

### 3.1 波次（Wave）

| Wave | 并行内容 | 出口 |
|---|---|---|
| **W0** | 本计划生效；S0 共享接口清单冻结；HTML sanitizer 政策段落定稿 | 可开工 A–D、E、H |
| **W1** | A HTML ∥ B DOCX ∥ C XLSX ∥ D PPTX ∥ E ASR ∥ H Agent（文档类） ∥ **P PDF-VIS** | 各线各自 gate；S0 合入无冲突 |
| **W2** | F Audio ∥ G Video（E 已绿）∥ H Agent 扩展 | 音视频闭环 + Research 覆盖新 locator |
| **W3** | I 全混合 + J 总验收 | V5-F engineering 收尾 |

说明：W1 内文档四线**允许真正并行**；W2 不得在 E 未绿时 enable Audio/Video。

## 4. 线卡（Lane cards）

### 线 A — F-HTML

| 项 | 内容 |
|---|---|
| 目标 | `html`（或批准的 kind 名）生产闭环 |
| 前置 | sanitizer/resource 政策写入 OD-B5 批准正文 |
| 拥有 | adapter、locator `html_anchor`、sanitize、Viewer、fixtures、测试 |
| 禁止 | 执行 script；远程活动内容默认拒绝 |
| 依赖 S0 | locator union / catalog row |
| 出口 | F-G-HTML |

### 线 B — F-DOCX

| 项 | 内容 |
|---|---|
| 目标 | `docx` 生产闭环 |
| 前置 | W0；无宏执行；加密文件 fail-closed |
| 拥有 | 解析、normalized 文本/结构、`docx_anchor`、Viewer、测试 |
| 共享 | 若抽 OOXML 公共库，须 S0/shared owner 指定唯一写入方 |
| 出口 | F-G-DOCX |

### 线 C — F-XLSX

| 项 | 内容 |
|---|---|
| 目标 | `xlsx` 生产闭环 |
| locator | `xlsx_range`（sheet + 单元格范围 + text hash） |
| 禁止 | 重算不可信宏；与 docx 业务逻辑交叉改文件 |
| 出口 | F-G-XLSX |

### 线 D — F-PPTX

| 项 | 内容 |
|---|---|
| 目标 | `pptx` 生产闭环 |
| locator | `pptx_slide` / `pptx_shape`（冻结名以 brief 为准） |
| 出口 | F-G-PPTX |

### 线 E — F-ASR

| 项 | 内容 |
|---|---|
| 目标 | ASR capability：配置则可用，未配置则稳定错误码；**无假 adapter** |
| 拥有 | capabilities/errors/readiness、fingerprint、timeout、secret 边界 |
| 禁止 | 在 E 未完成时 enable `audio`/`video` catalog |
| 出口 | F-G-ASR |

### 线 F — F-AUDIO

| 项 | 内容 |
|---|---|
| 前置 | E 绿 |
| 目标 | `audio` + `audio_range` + 转写 ContentUnit + 播放器 |
| 出口 | F-G-AUDIO |

### 线 G — F-VIDEO

| 项 | 内容 |
|---|---|
| 前置 | E 绿 |
| 目标 | `video` + 时间段/帧 locator + keyframe + 播放器 |
| 禁止 | 注册成 audio+封面 |
| 出口 | F-G-VIDEO |

### 线 H — F-AGENT（伴随）

| 项 | 内容 |
|---|---|
| 目标 | 固定 DAG 下多模态 evidence 完善（非新平台） |
| 范围 | search/cite/open、bundle 分组、时间/文档 chip、scripted Research E2E |
| 禁止 | 新 step kind、动态图、自由工具、provider selector |
| 节奏 | W1 跟文档类；W2 跟音视频；W3 跟混合 |
| 出口 | F-G-AGENT（全启用 kind 上 A1–A8） |

### 线 I — F-MIX / 线 J — F-ACCEPT

| 线 | 目标 |
|---|---|
| I | 全启用 kind 一键 seed + empty-target restore + zero residue |
| J | 全量 API/Worker/Web + Critical；质量门保持 not_evaluable |

## 5. 共享内核 S0（必须串行）

下列路径/主题 **默认禁止双人并行改**，由 main controller 指定 **唯一 shared owner**，其它线只提 PR/变更请求：

| 主题 | 典型位置（示意） |
|---|---|
| Modality registry 组装 | `modalities/registry.py` 等 |
| Catalog / Alembic 启用行顺序 | `alembic/versions/*`、catalog models |
| OpenAPI / DTO locator union | API schemas、Web evidence parsers |
| Retrieval channel 注册与融合 | `services/retrieval.py` |
| Ingestion orchestrator  seam | `services/ingestion.py`、worker 公共入口 |
| Citation envelope（仅允许扩 union） | chat/citation schemas |

规则：

1. 模态线先在**自己目录**完成 adapter/locator/codec。  
2. 需要挂 registry/union 时，提交 **S0 合入清单**（字段、kind 字面量、测试名）。  
3. S0 owner **按队列**合入，一次一个 kind 或一批已审过的 patch。  
4. 冲突时：**合同正确性 > 速度**。

## 6. 工作树与协作纪律

- 默认 **一个 canonical worktree**（`/home/cc/code/citeframe`）。  
- 并行靠 **文件集不重叠** 的 lane，不靠多 worktree 互踩。  
- 若必须开第二 worktree：main controller 书面批准 + 文件所有权表。  
- 不 commit/push，除非主人当轮明确要求。  
- 无效假设导致的临时代码：验证失败后应删除，不留兼容层。

## 7. 优先级与不做清单

### 7.1 P0

V5-F 模态分线收尾（本文）。

### 7.2 明确后置 / 不做

| 项 | 态度 |
|---|---|
| 付费 formal R803 | 暂缓（主人已决定） |
| M404 用户价值 | 后置 |
| 通用 Agent 平台 / 动态 DAG | 不做（OD-C7） |
| Provider 选择器 UI | 不做（OD-C6） |
| 未闭环就 enable 上传 | 禁止 |

## 8. 状态板（开工后维护）

| 线 | 状态 | Owner | 当前阻塞 | 出口证据路径 |
|---|---|---|---|---|
| W0 / S0 | accept | main controller | — | 本文件 + sanitizer 政策段落 |
| A HTML | accept | | | `docs/evals/artifacts/…` |
| P PDF-VIS | accept | | | `pdf-in-page-visual-v1.md` |
| B DOCX | accept | | | |
| C XLSX | accept | | | |
| D PPTX | accept | | | |
| E ASR | accept | | | |
| F AUDIO | blocked-on-E | | E | |
| G VIDEO | blocked-on-E | | E | |
| H AGENT | accept | | | |
| I MIX | accept | | A–G | |
| J ACCEPT | blocked-on-I | | I | |

状态枚举：`pending | in_progress | blocked | review | accept | cancelled`。

## 9. 与旧「建议串行顺序」的关系

[`implementation-lanes-v5f.md`](implementation-lanes-v5f.md) 早期写过 DOCX→XLSX→PPTX **串行**建议。  
**本文件为并行执行的权威覆盖**：文档族 **允许并行**；仅 S0 与 ASR→音视频 保持串行依赖。  
字段级合同仍以 `v5f-detailed-spec.md` 为准；本文件管 **怎么拆线、怎么并行、怎么收尾**。

## 10. 开工检查单（W0）

- [ ] 主人确认按本并行计划执行（本文 status 保持 owner-aligned）  
- [x] HTML sanitizer/resource 政策写入可引用段落（OD-B5 正式批准正文）  
- [ ] S0 共享文件清单 + shared owner 姓名/角色  
- [ ] 各线 owner 与「禁止改动路径」表填进 §8  
- [ ] 明确第一波并行集合：默认 `A+B+C+D+E+H`  
- [ ] 实现开始前：`git status` 分类、身份与远程检查（仓库规则）

## 11. 相关文档

| 文档 | 角色 |
|---|---|
| [`decision-2026-08-13-v5f-scope.md`](decision-2026-08-13-v5f-scope.md) | 范围批准 |
| [`v5f-detailed-spec.md`](v5f-detailed-spec.md) | 字段与闭环合同 |
| [`implementation-lanes-v5f.md`](implementation-lanes-v5f.md) | lane 职责底表 |
| [`verification-matrix-v5f.md`](verification-matrix-v5f.md) | 验收门 |
| [`plan-audit-v5f.md`](plan-audit-v5f.md) | 计划审计 |
| [`grok-handoff-v5f.md`](grok-handoff-v5f.md) | 实现 handoff |
| [`docs/architecture/modality-extension-contract.md`](../../../docs/architecture/modality-extension-contract.md) | 内核扩展协议 |
