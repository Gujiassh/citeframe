# V5-B / V5-C Open Decisions

## 使用规则

状态只能是：`open`、`approved`、`rejected`、`superseded`。

- `open` 的 decision 不得被 worker 当成默认实现事实。
- 任何影响数据库、OpenAPI、locator literal、Research ledger、Citation/NoteSource、Chat SSE 或成本/权限含义的选择必须先变为 `approved`。
- 推荐方案只是评审材料，不是批准结果。
- 批准后必须在本文件写入日期、批准人、影响范围、需要同步的 spec/lane/test 文件。

## OD-B1：第一种生产新模态

状态：`approved`

批准：2026-08-05，第一生产新模态采用 Markdown-only `document` slice；HTML、Office 不进入本轮。HTML 另走 OD-B5 和独立 enablement gate。

推荐：先做 `Markdown`，HTML 作为同一类 document 的第二个 enablement slice；Office 不进入第一轮。原因是 Markdown 的结构、锚点和安全边界可控，HTML 需要额外冻结 sanitizer、外链资源、脚本、CSS、编码和可视化策略。

实现影响：

- `Markdown only` 可先冻结 `document` asset kind 的最小文本/结构合同。
- HTML 若单独开启，必须新增 HTML sanitizer policy、资源拒绝/下载规则和独立 fixtures；不能因为 MIME 已加入就自动启用。
- Office 必须另写 modality brief，不得塞进 document adapter 的未验证分支。

## OD-B2：Document locator literal 与详细语义

状态：`approved`

批准：2026-08-05，v1 使用 `document_anchor`，detail family=`record`；Document identity 复用公共 `evidence_locators.asset_id` + generation/representation snapshot，不新增平行 document 主键。v1 单 range，禁止 multi-range。

冻结字段：

- `block_id`：由 source SHA + parser version + canonical block identity 稳定生成；
- `block_kind`：`heading | paragraph | list_item | code_block | quote | table`；
- `heading_path`：schema-validated ordered string array；
- `char_start`、`char_end`：相对于 `document-normalization-v1` canonical text，`char_end > char_start`；
- `text_sha256`：canonical block text hash；
- `normalization_version`：固定为 `document-normalization-v1`。

问题：Document 来源定位使用 heading path、稳定 block ID、字符范围，还是它们的组合？

推荐候选：新增一个版本化 `document_anchor` locator，detail family=`record`。公共 `evidence_locators.asset_id` 与 generation/representation snapshot 已经表达 document identity；本节的 `document_id` 仅表示该 Asset identity，不新增一个平行 document 主键。detail 至少冻结：

- `block_id`（parser 在同一 source bytes + parser version 下稳定生成）
- `block_kind`：`heading | paragraph | list_item | code_block | quote | table`
- `heading_path[]`
- `char_start`、`char_end`（相对于规范化 document text）
- `text_sha256`
- `normalization_version`

禁止只保存 CSS selector、DOM index 或当前渲染树 offset；这些可以作为 Web renderer hint，但不能是 Evidence 真相。

实现影响：新增 locator detail 表、DTO discriminator、codec、clone/recovery fixtures；必须先确定字段名和是否允许多范围。

## OD-B3：第一轮 Document 是否允许数据库迁移

状态：`approved`

批准：2026-08-05，允许 additive typed tables/catalog rows：Document 专用 Representation/ContentUnit/locator detail 与 catalog rows 可以新增；不修改已有 Asset、Citation、NoteSource、Quick Chat、Research ledger 的核心列、保存语义或历史数据。migration、OpenAPI discriminator、backup/restore 和 mixed-workspace regression 必须同一 slice 交付。

问题：是否批准为 document 增加类型化 Representation/ContentUnit/locator detail 表和 catalog rows？

推荐：批准 additive typed tables/catalog rows，不修改已有核心表列，不修改 Citation/NoteSource 列，不做旧数据重写。若不批准迁移，B003 只能停留在 brief/fixture，不能生产启用。

## OD-B4：Document 检索通道

状态：`approved`

批准：2026-08-05，Document v1 只注册现有 `text` embedding space + lexical channel；不新增视觉/音频向量空间。ContentUnit/Representation/locator 使用 registry type signature 约束检索。

推荐：第一轮只使用既有 `text` embedding space + lexical channel；ContentUnit 的 `unit_kind` 和 Representation kind 通过 registry signature 进入 scope。不要为 Markdown/HTML 引入新的向量空间。

## OD-B5：HTML 安全和资源政策

状态：`rejected`

范围说明：HTML 未进入 Markdown-only 第一 slice；重新启用 HTML 必须批准 sanitizer/resource policy、fixture、restore 和独立 enablement gate。

## OD-B6：Audio 进入生产的前置条件

状态：`open`

Audio 不能因为 B004 已列在 tasks 就进入 registry。必须先完成 ASR capability contract：provider/model/version、secret boundary、duration/cost limit、segment schema、fingerprint、timeout、error codes 和 no-fallback behavior。

## OD-B7：Video 是否和 Audio 共用转写 ContentUnit

状态：`open`

推荐：共用文本检索语义但保留 `asset_kind` 专属 ContentUnit/locator kinds；Video 必须额外保存 keyframe/shot 表示和 frame/time locator，不把视频简化成 Audio。

## OD-C1：V5-C 是否纯产品化 delta

状态：`open`

推荐：`pure productization delta`。V4 fixed Research executor、ledger、Evidence-only tools、HITL、SSE、budget、retry/recovery 是基线；V5-C 只补用户入口、timeline、branch comprehension、control state、artifact/evidence drill-down 和 V5-A profile display residual。

不默认新增 step kind、动态 DAG、通用 Agent runtime、Research schema 重构或新的持久化事实。

## OD-C2：V5-C 第一轮用户可见缺口

状态：`open`

实现前需要用当前 production-start Web fixture 逐项确认：

- timeline 是否需要独立投影，还是现有 events/steps 足够；
- researcher branches 是否需要专门分组展示；
- evidence bundle、verification result、conflict report 是否需要新 UI 入口；
- budget/cost 是否需要明细而非当前汇总；
- mobile viewport 的最小可用控制集合。

## OD-C3：Researcher retrieval top-k 语义

状态：`open`

必须明确 `researchExecution.execution.provider.retrievalTopK` 是否就是所有 researcher evidence search 的上限。当前 worker 有局部 `top_k=8` 代码事实；在未裁决前不能在产品文档声称所有节点严格使用快照 top-k，也不能随意改 production behavior。

## OD-C4：非 OpenAI provider 的 Research pricing

状态：`open`

V5-A 已支持 DeepSeek generation，但 Research pricing book 的支持范围需要逐 provider/model 冻结。推荐：没有价格条目时在 reserve 前 fail-closed 为明确 `provider_pricing_not_configured`，不估算为零、不偷偷复用 OpenAI 价格。

## OD-C5：V5-C 的 R800 复验范围

状态：`open`

推荐：若只改 Web presentation 且不改 runtime/save/recovery contract，执行 focused Research E2E + full API/Worker/Web；若改 budget、permission、lease、event replay、artifact publication 或 recovery，重新执行对应 R800 scenario，必要时运行完整 R800 acceptance。

## OD-C6：Provider selector

状态：`rejected`

范围说明：仅针对当前 slice；重新打开必须新增 decision 和影响评审。

V5-A/V5-C 不开放用户或 Workspace provider selector。只有新增 decision、API/persistence/permission/cost contract、migration impact 和独立批准后才能重新打开。

## OD-C7：通用 Agent 平台

状态：`rejected`

范围说明：仅针对当前 slice；重新打开必须新增 decision 和影响评审。

不做动态工作流编辑器、无限递归 Agent、自由插件、模型生成 graph、任意网络/Shell/ORM 工具或隐式长期记忆。

## OD-C8：Research role-I/O contract version

状态：`open`

当前 production runtime 使用 `GenerationResearchAgents.DEFAULT_AGENT_RESULT_SCHEMAS` 和现有 runtime adapter；`research-agent-results-v1` 的 strict validator/schema 在当前评估/contract code 中不是已批准的 production binding。V5-C 必须二选一：

- 推荐纯 productization 路径：保持当前 production role-I/O 和 prompt variables 不变，文档/fixtures 以当前 runtime contract 为准；
- 新 schema 路径：批准新的 production schema version，冻结 prompt variable binding、validator、runtime adapter、server-generated IDs、API persistence mapping、Web fixtures 和 migration/save impact。

在 OD-C8 批准前，C-G3 只能做现有 production contract inventory，不能声称 strict V1 已进入 Research production。
