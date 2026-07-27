# V4 需求发现：后续多模态与受控多 Agent 研究

## 状态与使用方式

- 状态：产品方向与 R000 字段/API/状态机合同已批准；R000 批准不是实现授权。
- 建立日期：2026-07-24；产品方向批准日期：2026-07-25；R000 合同批准日期：2026-07-27。
- 适用范围：在 V4 R000 字段级数据、API、状态机和事件合同之前，明确产品要解决的问题、用户流程、模态进入门和 Agent 边界。
- 不产生实现授权：2026-07-25 的批准只关闭 RD002，不批准新增表、字段、API、SSE、保存语义、模型 provider 或外部网络访问。
- 权威关系：当前产品事实以已通过 RD003 核对的 `docs/ssot/`、`docs/architecture/`、已完成 V3 规格和运行证据为准；第 11 节项目已全部关闭，后续若当前态再漂移必须重新审查。本文件只记录后续决策输入和待裁决项。

## 1. 当前基线

Citeframe 当前定位是面向 AI/软件工程师与技术研究者的证据型研究工作台。核心任务不是“支持多少文件格式”，而是把多份复杂资料转化为可核验、可复用的技术判断：

`提问 -> 获得有证据支持的回答 -> 打开原文核验 -> 形成结论 -> 继续追问或保存`

当前事实：

- PDF 已有文本、扫描 OCR、布局、表格/图表区域、页面/区域 Evidence、检索、Citation、Viewer、删除和恢复链。
- Image 已通过 M403B 进入生产 registry，支持 PNG/JPEG/WebP、方向归一化、OCR/caption、区域 Evidence、区域 Chat/Note、Viewer、失败重试和备份恢复。
- Quick Answer 是默认主路径，当前 Chat、Citation、NoteSource、`assetScope`、SSE 和保存语义必须保持稳定。
- M404 真实用户价值仍为 `not_evaluable`，产品继续是 `internal_preview`。工程门通过不等于用户价值通过。
- V4 只能在现有 Asset/Evidence 主链上增加显式、受控的 Deep Research，不把产品扩张为通用 Agent 平台。

## 2. 战略结论与假设

### 2.1 产品假设

1. **证据闭环假设**：目标用户愿意为了更快、更可靠地核验原文，反复使用同一 Workspace，而不是只进行一次性聊天。
2. **深度研究假设**：复杂比较、综合、冲突分析和证据不足判断，可能需要比 Quick Answer 更长的受控流程；但用户必须明确选择并能看到成本、进度和证据依据。
3. **模态价值假设**：新模态只有在带来新的高频用户任务或显著降低现有任务成本时才值得接入；格式数量本身不是价值。

### 2.2 对 `/home/cc/tmp/555.txt` 的吸收与修正

`555.txt` 关于 Asset、Representation、ContentUnit、Embedding、EvidenceLocator 和分模态 adapter 的方向与当前 V3 架构一致；“先 PDF/Image，再音频/视频”的工程顺序也可作为候选路线。

需要修正的是产品承诺：文件、音频、视频和标注数据不能作为一个未经验证的“全模态产品”一次性承诺。Omnilabel 的标签体系、人工标注、模型预测、轨迹和聚合分析属于独立业务域，不是普通文件格式。

## 3. 目标用户与 JTBD

### 第一目标用户

- 需要审阅论文、技术规范、评测报告、设计方案和技术图片的 AI/软件工程师。
- 需要基于多份资料形成判断、比较方法并保留证据链的技术研究者。

### 核心 JTBD

当我需要基于多份复杂资料形成技术判断时，我希望快速得到有原文支持的答案，立即回到准确页码、区域或时间位置核验，并把结论和证据留在项目 Workspace 中，以减少手工翻找、重复查证和散落笔记。

### 暂不承诺的用户

- 合同、财务、法律和泛个人学习。
- 标注团队、数据集运营团队和需要复杂统计分析的 Omnilabel 用户；这些用户需要独立 discovery，不应被普通 Asset 上传入口吸收。

## 4. 产品线拆分

### 4.1 当前多模态核心：PDF + Image

PDF 和 Image 已是当前可用能力，不应在下一阶段重复建设“再做一遍多模态基础”。后续工作应优先验证它们是否真的改善研究任务：

- 引用是否能被用户打开并快速核验。
- 表格、图表、扫描区域和图片区域是否仍有稳定定位缺口。
- 多资产比较是否比普通 Chat 更快形成可提交结论。
- 结论是否会被保存、复用和带回同一 Workspace。

### 4.2 后续文件/媒体模态：逐个立项

下表是候选需求框架，不是已批准的优先级或数据合同。每种模态都必须先写出首个用户任务和停止条件。

| 候选模态 | 首个应验证的用户任务 | Evidence locator / Viewer | 检索通道 | 主要成本与风险 | 进入门 |
| --- | --- | --- | --- | --- | --- |
| Markdown/HTML | 在技术资料库中按章节、链接和代码片段比较方案 | heading/anchor/DOM 区域；结构化文本 Viewer | FTS + Dense + 标题/链接过滤 | 结构保真、动态 HTML、外部资源 | 至少一组真实技术资料任务证明比复制粘贴更快 |
| DOCX/PPTX | 在规范、设计文档和演示稿中定位段落、表格或 slide 证据 | paragraph/table-cell/slide 区域；分页或 slide Viewer | 文本/表格 channel + 元数据过滤 | 版式、表格和 slide 结构解析 | 有真实资料来源和定位 fixture；不把 Office 统称成一个模态 |
| XLSX/结构化表格 | 查询指标、比较列值和识别分布，而不是让模型猜总数 | workbook/sheet/cell/range；表格 Viewer | SQL/分析查询优先，文本检索辅助 | 公式、类型、聚合和权限语义 | 明确聚合查询合同和人工核验集后再进入 |
| Audio | 从访谈、会议或讲座中定位观点、说话人和时间段 | `audio_range` + speaker；可播放时间轴 | ASR/说话人文本 + 元数据 | ASR 错误、隐私、长时延和 provider 成本 | 真实音频任务证明时间段证据比文本摘要有额外价值 |
| Video | 找到镜头、关键帧、字幕和视觉事件并回到时间轴 | `video_range`/frame；视频时间轴 Viewer | ASR/字幕 + 关键帧/镜头 + 元数据 | 解析、存储、视觉检索和移动端体验成本高 | 先有明确视频任务、时间定位黄金集和成本上限 |
| Omnilabel / 标注记录 | 比较人工标签、模型预测、轨迹和数据集质量 | record/field/path/interval；结构化分析 Viewer | SQL/分析引擎 + 受控语义检索 | 权限、schema、统计正确性和独立业务流程 | 独立用户研究、schema、权限和分析合同；不从普通文件入口进入 |

### 4.3 已批准的方向顺序

在没有真实用户数据时，建议优先按“离当前 JTBD 的距离”和“验证成本”排序，而不是按媒体炫技程度排序：

1. 先用现有 PDF/Image 验证 Deep Research 是否改善复杂研究任务。
2. 若资料接入是主要瓶颈，优先评估 Markdown/HTML 与 DOCX/PPTX；它们更接近当前技术研究资料流。
3. Audio 只有在访谈/会议/讲座任务明确后进入；Video 依赖更高成本的时间轴和视觉证据验证。
4. XLSX、结构化记录和 Omnilabel 以分析产品能力单独评估，不与通用文件上传打包。

Owner 已批准先验证现有 PDF/Image 上的 Deep Research，再优先评估 Markdown/HTML 与 DOCX/PPTX 的文档便利性路线。Audio/Video 保持独立候选，不与文档路线同时隐式开工；任何新模态仍需单独 modality brief 和实现审批。

### 4.4 每种新模态的统一进入门

新模态进入实现前，必须有一份独立的 modality brief，至少包含：

1. 目标用户、第一 JTBD、输入样本和不做的任务。
2. 输出 Representation、ContentUnit 和类型化 Evidence locator 的用户可理解语义。
3. Viewer、选择/高亮交互、移动端行为和失败态。
4. 检索 channel、过滤语义、结构化查询边界和无答案处理。
5. 分层黄金集：解析、定位、检索、回答、拒答分别评分。
6. 延迟、存储、provider、隐私、保留和单位成本上限。
7. 删除、重处理、历史 Citation/NoteSource、备份恢复和权限影响。
8. 价值门：真实任务完成率、核验后耗时、定位准确率或其他明确业务结果。

没有通过这份进入门，不创建上传入口、数据库启用行、Worker adapter 或 Viewer renderer。

## 5. Quick Answer 与 Deep Research

### 5.1 Quick Answer（默认）

1. 用户进入 Workspace，选择全部 ready Asset 或显式 Asset 范围。
2. 用户提交问题，可带已有输入 Evidence；请求继续走现有 Chat 流。
3. 回答流式返回，Citation 可跳转到 PDF/Image Evidence Viewer。
4. 用户自行决定追问、打开原文或保存 Note。
5. 不显示研究计划审批、Agent DAG、研究成本或后台研究状态。
6. 不因问题看起来复杂而自动升级；Quick 与 Deep 的请求、历史、Citation、NoteSource 和恢复语义不能互相伪装。

### 5.2 Deep Research（显式选择）

1. 用户在输入区明确切换到 Deep Research，确认问题和证据范围。
2. Planner 生成结构化研究计划草案，只包含受限子问题、证据范围和预期缺口。
3. Create 和每次计划修订先冻结 planning snapshot；用户批准时只校验并精确复制该 snapshot 为 execution snapshot，不能重新解析 latest Asset/config。
4. 固定流程执行：`Planner -> bounded Researcher fan-out -> Verifier -> Critic -> 必要 HITL -> Synthesizer -> ResearchArtifact`。
5. 页面展示用户可理解的阶段、并行进度、Evidence 数量、错误和等待审批，不把 Agent 数量或图框架当作卖点。
6. 最终 Artifact 是独立、可追溯的研究产物，包含结论、Evidence、冲突/缺口和版本信息；不会自动写 Note、改写 Workspace 事实或替换原 Chat。
7. 只有被 Verifier 支持的 claim 才能进入最终报告；证据不足必须明确标记不足，不能由 Synthesizer 补全。

### 5.3 运行中预期

| 情况 | 用户可见结果 | 产品不应做的事 |
| --- | --- | --- |
| 计划待批准 | 显示计划草案和批准/修改/取消动作 | 未经批准直接消耗完整研究预算 |
| 某分支失败 | 标记失败分支和原因，允许限次重试 | 重跑全部分支或静默降级为 Quick |
| 需要人裁决 | 停在持久化 checkpoint，显示冲突/证据缺口 | 自动替用户决定冲突结论 |
| 客户端断线 | 运行继续，重连后按持久化事件序列续播 | 把断线当作运行取消或丢失进度 |
| API/Worker 重启 | 从同一 checkpoint 恢复，已完成步骤不重复 | 重复写入 Step/Event/Artifact |
| 用户取消 | 停止新工作，保留审计记录，不发布半成品 | 自动恢复、自动转 Quick 或伪造完成 |
| 关键证据不足 | 产出带明确缺口的非最终结果，或不发布最终 Artifact | 生成无证据的确定性结论 |

## 6. 受控多 Agent 边界

### 6.1 产品运行时角色

- 一个 Planner：只产出结构化计划。
- 有界数量的 Researcher：按子问题并行调用已注册 Evidence search/load 工具。
- 一个 Verifier：判定 claim 与 EvidenceLocator 的支持关系。
- 一个 Critic：记录冲突、缺口和需要人工裁决的问题。
- 一个 Synthesizer/Publisher：只使用通过验证的 claim 生成 Artifact。

禁止自由递归委派、无限循环、任意第三方插件和运行时任意代码加载。Agent 不得直连 ORM、MinIO、Shell、任意网络或未批准 provider。用户输入、资产内容和检索文本均是不可信数据，不能改变权限、预算或工具 allowlist；不得持久化思维链。

### 6.2 工程交付协作（与产品运行时分开）

R000 合同获批后，采用主控 + 有界并行 lane：

- API/账本 lane：运行记录、权限、幂等和 API 合同。
- Worker/执行 lane：固定 DAG、工具边界、重试、预算和恢复。
- Web/BFF lane：模式选择、运行状态、审批、Artifact 和 Evidence 跳转。
- Evaluation/Review lane：fixture、质量/成本/恢复指标、Critical review 和 Playwright 证据。
- 主控负责架构、跨 lane 合同、风险决策、集成和最终验收。

各 lane 不共享未批准的数据结构，不同时编辑同一合同文件；每个 slice 必须回写 spec/SSoT、测试和运行证据。主控不能只凭 Agent 汇报接受结果，必须检查 diff、运行验证和跨层合同。

## 7. MoSCoW 范围

### Must

- 默认 Quick Answer 不变，Deep Research 必须显式选择。
- Deep Research 有计划审批、冻结输入范围、固定 DAG、有界并行和 Evidence-only tool registry。
- Verifier fail-closed；unsupported claim 不得进入最终 Artifact。
- 支持取消、超时、限次重试、断线重连和 API/Worker 重启恢复的产品预期。
- ResearchArtifact、Evidence provenance、冲突/缺口和版本信息独立于 Note 保存。
- 每种新模态先完成独立 brief、黄金集、成本/安全评审和价值门。
- 工程门、模型质量门和 M404 用户价值门分开报告。

### Should

- 研究运行历史、阶段时间线、Evidence 数量和失败原因可读。
- 用户能查看 Quick 与 Deep 的结果差异，但不把两者结果混存成同一种消息。
- 研究产物可回到既有 Evidence Viewer，用户可主动将结果转存为 Note。
- 运行、Prompt、Workflow、provider/model 和评测输入都可追溯。

### Could

- 经过真实任务验证后，提供研究模板、领域化计划提示或 Artifact 对比视图。
- 在独立立项后增加 Audio、Video、Office、结构化分析的专用工作区体验。

### Non-goals

- 通用 Agent 平台、拖拽式 Workflow 编辑器、自由插件市场和任意网络浏览。
- 自动长期记忆、自动写 Note、自动修改 Workspace 事实或持久化思维链。
- Quick 自动升级、Deep 自动降级、跨 Workspace 联邦研究。
- 一次性承诺 Audio、Video、Office、结构化记录和 Omnilabel 的“全模态”覆盖。
- 没有评测缺口就引入统一向量空间、reranker、GraphRAG 或独立向量数据库。

## 8. 成功指标与验证顺序

### North Star（待定量化）

完成一个关键陈述均有证据支持、用户完成过原文核验并能复用结论的真实研究任务数。

### 指标组

- 质量：claim support rate、Evidence recall/precision、locator accuracy、冲突发现率、无证据拒答率。
- 用户行为：首次得到可核验答案耗时、核验后任务耗时、Citation 打开率、结论转 Note 率、同一 Workspace 的复用。
- 工程：完成率、失败分支重试率、恢复成功率、SSE 重放完整性、重复 Event/Artifact 数量、p50/p95 wall time、真实并行重叠。
- 成本与信任：token/provider 调用、预算取消率、人工等待、跨 Workspace 拒绝、工具策略拒绝、prompt injection 拦截。

### 验证顺序

1. 先使用同一 PDF/Image fixture、Asset scope 和 provider/model 建立 Quick baseline。
2. R100 先冻结 Research case、claim/evidence 标签、失败 taxonomy 和 scorer；R300/R400 可运行后，再用相同条件执行 Deep Research，并在 R800/R700 比较质量、耗时、成本和恢复。scripted provider 结果不解释为模型质量。
3. 通过内部工程验收后，继续按 M404 协议招募真实目标用户；没有真实用户时只能记录内部预评估，不能改变 `internal_preview`。
4. 只有某一新模态的真实任务明确受益，才为该模态启动独立实现阶段。

## 9. 主要风险与最小验证

| 风险 | 预演结论 | 最小验证 |
| --- | --- | --- |
| 用户不愿等待 Deep Research | 复杂任务价值不足以覆盖等待和成本 | 以现有 PDF/Image 做同题 Quick/Deep 对照，记录核验后耗时和结论采用率 |
| Agent 只是增加复杂度 | 多 Agent 不优于单 Agent | 固定 fixture 比较 Quick、单 Agent Research 和 bounded 多 Agent Research |
| 新模态只是格式堆砌 | 没有新的高频任务 | 为候选模态各写一个真实任务和停止条件，未满足不开发 |
| Evidence 看似完整但不可信 | unsupported claim 或 locator 漂移 | Verifier fail-closed、源重处理/删除/恢复后 provenance 回放 |
| 成本或失败不可控 | 并行放大 provider 调用和重试 | 预算、并发、超时和分支重试的工程 fixture |
| Omnilabel 拖偏产品 | 结构化分析需求吞噬通用研究工作台 | 独立用户/权限/schema/SQL discovery，不进入普通 Asset roadmap |

## 10. 产品方向审批记录

Owner 于 2026-07-25 回复“开始 批准”，按上一轮明确列出的推荐方案关闭 RD002。该批准范围如下：

| ID | 产品裁决 | 状态 |
| --- | --- | --- |
| D001 | 产品继续以证据型技术研究工作台为主线；Omnilabel 保持独立产品轨道 | approved |
| D002 | 先在现有 PDF/Image 上验证 Deep Research，再决定新增模态 | approved |
| D003 | 新模态先评估 Markdown/HTML 与 DOCX/PPTX；Audio/Video 分别立项 | approved |
| D004 | Quick 默认；Deep 显式 opt-in；计划必须人工批准；Research 不自动写 Note | approved |
| D005 | V4 Agent 只允许 Evidence search/load；不开放任意网络、插件、Shell、ORM/MinIO 直连或思维链持久化 | approved |
| D006 | 发起人批准计划并可取消自己的运行；Workspace owner 可因成本或安全终止任意运行 | approved |
| D007 | M404 沿用现有真实用户协议；未通过前保持 `internal_preview` | approved |

### 10.1 R000 合同审批记录

Owner 于 2026-07-27 在明确的“批准 `AP001-AP012` 推荐默认；例外：无”请求后回复“批准”。
[r000-approval-record.md](r000-approval-record.md) 记录精确输入 hash、全部获批决策、独立评审证据和未授权范围。
本次决定批准 Research Artifact 保留/删除、源 Asset 删除后的解释能力、外部 provider 数据边界、字段级
schema、状态机、API、独立 Research SSE、幂等和 Quick 不变 oracle，但不授权任何实现、部署或 provider 启用。

## 11. RD003 当前态文档漂移清单

本清单是 R000 前置证据，不把历史阶段文字机械改写成当前事实。每项必须决定“修正为当前态”或“明确标为历史”，并由独立 reviewer 复核后才能关闭 RD003。

| 文档/段落 | 漂移 | 处理决定 | 状态 | 关闭证据 |
| --- | --- | --- | --- | --- |
| `docs/ssot/system-architecture.md:150-172` | 当前前端架构仍混用 Documents hooks 与 PDF-only Viewer 目标态 | 对照当前 Asset hooks、EvidenceViewer 和 PDF/Image renderer 修正；历史组件说明单独标注 | closed | current-state diff + `m403b_deploy_config` independent code review 2026-07-25 |
| `docs/ssot/system-architecture.md:220-227` | 当前 API 服务层仍定义 Document/page/chunk 状态与删除职责 | 对照当前 Asset lifecycle、Representation、ContentUnit 与 delete cleanup 修正 | closed | current-state diff + `m403b_deploy_config` independent code review 2026-07-25 |
| `docs/ssot/system-architecture.md:282-291` | Worker task 同时列出旧 `parse_pdf/chunk_document/delete_document_artifacts` 与当前 Asset jobs | 删除当前态歧义；历史任务单独标记，当前只保留 registry-driven Asset adapter 与 job 语义 | closed | current-state diff + `m403b_deploy_config` independent code review 2026-07-25 |
| `docs/ssot/system-architecture.md:398-410` | 存储内容与对象路径仍是 PDF-only `documents/{documentId}` | 对照当前 Asset/Representation 对象键修正或标记为 V1 历史建议 | closed | current-state diff + `m403b_deploy_config` independent code review 2026-07-25 |
| `docs/ssot/system-architecture.md:636,646` | trace 与上传流程仍使用 `document_id/document` | 修正为当前 `asset_id`、Asset 与 Representation/ContentUnit 语义 | closed | current-state diff + `m403b_deploy_config` independent code review 2026-07-25 |
| `docs/architecture/feature-map.md:3-41` | 当前能力树标题仍以 PDF/page/chunk 为主，和后文 Asset/PDF+Image 当前事实并列 | 重写当前能力树，并分开 M403B 工程完成、M404 not_evaluable 与 R000 未批准状态 | closed | current-state diff + `m403b_deploy_config` re-review passed 2026-07-25 |
| `docs/ssot/product-design.md:240,268,336-338` | Image/V3 被写为待完成 | 已同步为 M403B 已启用、V3 已完成、V4 为下一阶段 | closed | 本次 diff + independent review |
| `docs/architecture/api-contracts.md:160,191` | Image 与 M304B 仍被写为未开放 | 已同步为 M403B/M304B 当前合同 | closed | 本次 diff + independent review |
| `docs/architecture/multimodal-asset-target-design.md:6` | 仍称只有 PDF 启用摄取 | 已同步为 PDF/Image 均已生产启用 | closed | 本次 diff + independent review |

R000 approval record 还必须明确：本文件中的 `audio_range`、`video_range`、heading/anchor 和 workbook/sheet/cell/range 都只是产品定位示例，不能直接复制为数据库字段、API DTO 或 locator schema。

## 12. 下一步门禁

当前推进 R100 评测基线；R000 两阶段 Git 恢复点已完成：

1. 产品方向 RD002 已关闭；产品裁决发生变化时必须更新第 10 节 decision record。
2. `RD003` 已于 2026-07-25 经独立 code-backed review 关闭；R000 只可基于当前 Asset/Evidence 事实源设计，不能重新引入旧 Document/PDF-only 当前态描述。
3. R000 `AP001-AP012` 已于 2026-07-27 全部按推荐默认批准、无例外；冻结输入保留审批前状态文字，批准事实只由 `r000-approval-record.md` 表达。
4. contract snapshot commit A=`466e5a3` 与 approval record commit B 已形成；B 不记录自身 SHA，避免 Git commit 自引用。
5. 当前推进 R100 Evaluation-first baseline，完成 fixture、scorer、可重放 Quick baseline 和运行边界。
6. R100 全部通过后，R200/R300 依照已批准合同直接实现，不再重复请求产品决策。
7. 新模态另建 modality brief；不得把模态实现与 Research 账本合同混在同一未批准 slice。

本文件中的候选模态 locator 和未进入 D001-D007 的建议不构成开发计划或字段/API 合同承诺。
