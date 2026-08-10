# 功能地图

## 1. 当前产品能力

```text
Citeframe
├─ 账号与 Workspace
│  ├─ 登录 / 会话 / 隔离
│  ├─ Workspace 创建 / 切换 / 归档
│  └─ Prompt 与检索配置
├─ PDF / Image Asset 接入
│  ├─ 上传 / finalize / 失败重试 / 重建索引
│  ├─ 异步删除 / 清理重试 / 源完整性校验
│  └─ PDF 与 PNG/JPEG/WebP 类型门禁
├─ 类型化知识处理
│  ├─ PDF 文本层 / OCR fallback / 布局与区域
│  ├─ Image oriented Representation / 区域内容
│  ├─ Representation / ContentUnit / Embedding 版本边界
│  ├─ PostgreSQL lexical + pgvector Dense + RRF
│  └─ ingest / embed_chunks / delete_cleanup 状态机
├─ 证据问答
│  ├─ Chat-first 全部 Asset / 显式 Asset 范围问答
│  ├─ 流式回答 / 消息分支
│  ├─ pdf_page / pdf_region / image_region citation
│  └─ citation -> note / 标签 / 历史 Evidence
├─ Evidence Research
│  ├─ 显式 Quick / Research 模式
│  ├─ 冻结 Plan / Workflow / Prompt / Asset scope / provider profile
│  ├─ bounded Researcher fan-out / Verifier / Critic / Synthesizer
│  ├─ 计划审批 / 冲突裁决 / SSE replay / retry / cancel / lease reclaim
│  ├─ immutable Artifact / Claim / Evidence provenance
│  └─ owner-only Evaluation Dashboard
├─ Evidence Viewer
│  ├─ PDF.js 原文 / 目录 / 文本选择 / 区域高亮
│  ├─ Image Representation / 区域高亮
│  └─ Citation / NoteSource 定位与版本化 Evidence
└─ 运行基线
   ├─ 锁定镜像 / Alembic migration gate
   ├─ Prometheus / grep-friendly 日志
   ├─ PostgreSQL + MinIO 同批备份恢复
   └─ Caddy HTTPS 安全入口
```

以上是当前已实现事实。正式数据模型已经切换为 `Asset -> Representation -> ContentUnit -> EvidenceLocator -> Citation/NoteSource`；PDF 与 PNG/JPEG/WebP Image 都已进入生产摄取注册表，并共用稳定的 Asset/Evidence 主链。

## 2. 当前阶段：V4 基线完成，V5 能力主线启动

Asset 和 Evidence 主链、PDF/Image 生产 registry 与 V4 Research 工程闭环均已实现。R800 v4 在真实 PostgreSQL/MinIO 和生产镜像上通过并行、HITL、失败恢复、SSE replay、Artifact provenance、备份恢复与零残留清理。当前能力包括：

- PDF/Image 统一资产列表、上传、处理状态、重试和删除
- Chat 全部资产/显式资产范围
- 页面布局和段落区域
- OCR bbox 质量与坐标合同
- 表格结构、表头/行列关系和表格问题
- 图片/图表区域、描述和必要时的视觉检索
- 独立图片 OCR、caption、区域检索和查看
- `pdf_page / pdf_region / image_region` 类型化 locator
- citation 点击后的精确区域高亮
- 通用 Evidence Viewer，内部使用 PDF/Image 专用 renderer
- 文本、扫描页、表格、图表、独立图片和无答案问题的分层评测
- 独立 Research Run/Event SSE、版本化 Workflow/Prompt 与预算/调用账本
- 可信离线 Evaluation importer、owner-only API 与质量/成本/恢复下钻

Evidence 数据合同与迁移设计已经批准并实施。已有 locator 意义、Citation/NoteSource envelope 和保存语义继续冻结；后续仍不能引入任意 JSON locator 或绕过类型目录与 codec。

R800 使用 scripted provider，只证明工程行为；R803 真实模型成对质量与 M404 目标用户价值均保持 `not_evaluable`，产品仍是 `internal_preview`。它们是后置质量/发布证据，不阻塞 V5 功能建设。

## 3. V5 目标能力地图

```text
V5 capability-first
├─ Provider / Model Profiles
│  ├─ generation / embedding / vision / ASR capabilities
│  ├─ server-side profile、版本、成本与数据边界
│  └─ Run/Job 快照、能力校验与明确失败
├─ Modality Expansion
│  ├─ PDF/Image production baseline
│  ├─ Markdown/HTML 与批准的文档类 adapter
│  ├─ Audio transcript / speaker / time-range Evidence
│  └─ Video transcript / subtitle / keyframe / time-range Evidence
├─ Multi-Agent Productization
│  ├─ Quick / Research
│  ├─ Planner / Researcher / Verifier / Critic / Synthesizer
│  ├─ bounded parallelism / HITL / retry / recovery
│  └─ Artifact / Claim / Evidence / Note knowledge outputs
└─ Deferred Release Evidence
   ├─ R803 model quality by modality/task/provider
   └─ M404 real-user value and Beta/release decision
```

V5 目标能力复用 `Asset -> Representation -> ContentUnit -> EvidenceLocator` 和既有 Research ledger；不建设通用 Agent 平台，不把 Evaluation Dashboard 当作当前主产品入口。

## 3. 目标领域边界

- `Asset`：Workspace 下源资产身份、权限、生命周期和原始对象引用
- `Representation`：原文件、OCR、布局、表格、caption 等可版本化派生表示
- `ContentUnit`：段落、区域、表格、图像等可寻址检索/分析单元
- `Embedding`：ContentUnit 的可重建索引投影，不是业务真相
- `EvidenceLocator`：连接证据快照与源资产的类型化定位值
- `Citation`：回答生成时冻结 locator、展示摘要和索引映射的不可变证据快照

聚合、数量和分布问题走 SQL/分析路径；LLM 不得根据少量召回样本猜总量。模态入库适配器只产 Representation、ContentUnit 和 Locator，不把具体模态业务规则堆进 Chat 或共享容器。

稳定内核通过部署期封闭注册表调度模态模块。新增 Audio/Video/其他文件时增加 adapter、类型目录、类型化 locator、检索通道和 renderer，不修改 Asset、Chat scope、Citation、NoteSource 或 Evidence Viewer shell；未知或未启用 kind 明确失败，不接受任意文件猜测。

## 4. 远期与独立赌注

| 方向 | 定位 | 进入条件 |
| --- | --- | --- |
| Audio | ASR、说话人、时间段证据 | 单独用户任务与黄金集 |
| Video | 镜头、关键帧、字幕、时间段证据 | 单独成本和延迟门禁 |
| Omnilabel | 标签、预测、数据集质量和结构化分析 | 独立用户研究、权限与 SQL/分析架构 |

Omnilabel 不是“再支持一种文件”，而是另一个业务域；它不默认进入当前产品下一版本。

## 5. 变更门禁

新增能力必须：

1. 明确第一用户任务和可验证结果。
2. 写 feature spec、plan、tasks 和合同影响。
3. 涉及持久化/API/save 语义时先取得明确批准。
4. 用真实 fixture、指标、运行证据和旧/新 payload 比较验收。
5. 同步代码、测试、SSoT、运行手册和进度文档。
