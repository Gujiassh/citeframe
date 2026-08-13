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

状态：`rejected`（**V5-F 提议 reopen → approve**，见 `decision-2026-08-13-v5f-scope.md`；字段级 sanitizer 政策批准前不得实现）

范围说明：HTML 未进入 Markdown-only 第一 slice；重新启用 HTML 必须批准 sanitizer/resource policy、fixture、restore 和独立 enablement gate。

## OD-B6：Audio 进入生产的前置条件

状态：`open`（**V5-F 提议 approve after F-ASR freeze**；批准前不得 registry enable）

Audio 不能因为 B004 已列在 tasks 就进入 registry。必须先完成 ASR capability contract：provider/model/version、secret boundary、duration/cost limit、segment schema、fingerprint、timeout、error codes 和 no-fallback behavior。

## OD-B7：Video 是否和 Audio 共用转写 ContentUnit

状态：`open`（**V5-F 提议 approve as separate video kinds**；不得把 video 简化为 audio）

推荐：共用文本检索语义但保留 `asset_kind` 专属 ContentUnit/locator kinds；Video 必须额外保存 keyframe/shot 表示和 frame/time locator，不把视频简化成 Audio。

## V5-F proposed reopening (2026-08-13)

状态：`proposed`

主人要求补全多模态并完善 Agent 协作。完整决策与审计见：

- `decision-2026-08-13-v5f-scope.md`
- `v5f-detailed-spec.md`
- `implementation-lanes-v5f.md`
- `verification-matrix-v5f.md`
- `plan-audit-v5f.md`
- `grok-handoff-v5f.md`

Owner accepted V5-F scope on 2026-08-13 (implementation still paused). OD-B5/B6/B7 field-level freezes are authorized to be written as approved policy text at implementation start of each slice; until those policy paragraphs are committed, workers still must not enable registry rows.

## OD-C1：V5-C 是否纯产品化 delta

状态：`approved`

批准：2026-08-10。采用 `pure productization delta`，但同时批准一次有界的生产 Agent I/O 合同升级和 usage-first context/budget 合同升级；不重做 V4 executor。

V4 fixed Research executor、ledger、Evidence-only tools、HITL、SSE、retry/recovery 是基线。V5-C 补用户入口、timeline、branch comprehension、control state、artifact/evidence drill-down、V5-A profile display、版本化严格 role-I/O 和单次上下文 compact 门禁。

不新增动态 DAG、通用 Agent runtime、自由插件、provider selector、模型生成 graph、任意网络/Shell/ORM 工具或隐式长期记忆。

## OD-C2：V5-C 第一轮用户可见缺口

状态：`approved`

批准：2026-08-10。第一版使用现有 Events/Steps 的只读 server-seq projection，不新增另一套业务事实；Researcher branches 按 plan order 分组；展示 plan、evidence bundle、conflict report（有冲突时）和 final report；verification result 保持 internal；移动端支持状态查看、审批/修改、冲突处理、重试、取消和恢复；页面只显示 provider/model 与 usage，不显示任何 money/billing 字段。

## OD-C3：Researcher retrieval top-k 语义

状态：`approved`

批准：2026-08-10。`researchExecution.execution.provider.retrievalTopK` 是该 execution 中每次 Researcher evidence search 的冻结最大结果数；不是整个 Run 的证据总数。Worker 不得保留局部 `top_k=8` 常量，实际 result count 只进入 usage/telemetry。

## OD-C4：非 OpenAI provider 的 Research pricing

状态：`approved`

批准：2026-08-10。Research 启动和执行不依赖 pricing book；价格不属于本阶段用户界面，也不作为 Research budget gate。硬门禁使用 provider/tool calls、wall time、parallelism、attempt/retry 和单次模型 context/output limit。累计 input/output Token 只记录 usage，不终止 Run。未知价格必须保持 unknown/null，不写假零；R803/evaluation 的独立 cost contract 不变。

## OD-C5：V5-C 的 R800 复验范围

状态：`approved`

批准：2026-08-10。Web-only presentation 仍执行 focused Research production-start E2E + full API/Worker/Web；本轮因升级 role-I/O、context compact 和 usage-first budget，必须执行对应 R800 role-I/O/retry/recovery 场景；若验收发现持久化/recovery contract 改动，升级为完整 R800 acceptance。

## OD-C6：Provider selector

状态：`rejected`

范围说明：仅针对当前 slice；重新打开必须新增 decision 和影响评审。

V5-A/V5-C 不开放用户或 Workspace provider selector。只有新增 decision、API/persistence/permission/cost contract、migration impact 和独立批准后才能重新打开。

## OD-C7：通用 Agent 平台

状态：`rejected`

范围说明：仅针对当前 slice；重新打开必须新增 decision 和影响评审。

不做动态工作流编辑器、无限递归 Agent、自由插件、模型生成 graph、任意网络/Shell/ORM 工具或隐式长期记忆。

## OD-C8：Research role-I/O contract version

状态：`approved`

批准：2026-08-10。将严格 role schemas 提升为单一版本化 production contract；新 Run 只能使用批准版本。冻结 prompt variable binding、strict validator、runtime adapter、server-generated Claim IDs、API persistence mapping、Web fixtures 和 recovery/R800 impact。未知字段、重复字段、错误类型、跨 branch evidence 或 Claim set 不一致均 fail-closed。

该升级不新增 role kind、不改变 Citation/NoteSource/Quick Chat、不改 finished artifact bytes；历史 Run 通过 versioned contract registry 保持可读/可恢复，新 Run 不走旧合同 fallback。详细合同见 [`decision-2026-08-10-v5c-product-contract.md`](decision-2026-08-10-v5c-product-contract.md)。
