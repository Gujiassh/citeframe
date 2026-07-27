# RFC：PDF + Image Evidence 合同设计

## 状态

- 状态：Approved，2026-07-17
- 建立日期：2026-07-16
- 当前影响：批准合同已在 V3 Phase 1 完成 Asset/Evidence 数据、API、SSE、Viewer 与保存语义的一次受控切换；M403B 已在不改变 Citation、NoteSource、Chat 和保存语义的前提下启用 PNG/JPEG/WebP Image 摄取

## 1. 问题

本 RFC 起草时，citation 可以稳定回到 PDF 页码，但表格单元格、图表区域、图片和扫描文本块仍需要用户在整页中继续翻找；独立图片也没有正式 Asset、检索与引用闭环。V3 随后引入了 PDF/Image 区域级 Evidence，并保持历史回答、笔记来源、删除和重索引语义稳定。

本 RFC 不把系统一次性改造成全模态平台。V3 只讨论 PDF 与图片，以及 `pdf_page`、`pdf_region`、`image_region`；Audio、Video 和 Omnilabel 不进入。

## 2. 迁移前合同基线

Phase 1 实施前的事实：

- `documents` 是 Workspace 下的 PDF 资产和生命周期边界。
- `document_pages` 保存 1-based 页码、提取文本和扫描页 OCR blocks。
- `document_chunks` 保存页内字符范围、索引版本和 embedding 元数据。
- `message_citations` 保存 `document_id / chunk_id / page_number_snapshot / title / excerpt / index_version`。
- `note_sources` 从真实 citation 复制 `document_id / page_number / title / excerpt` 快照。
- Chat SSE 和历史消息 API 返回当前 `Citation` 结构。
- Viewer 使用 `documentId + pageNumber` 打开原始 PDF。
- 删除文档可以清理原文件、页面和 chunk，但历史 citation/note source 快照仍可读。

这些旧合同已按批准方案机械迁移；它们只作为历史语义 oracle，不再作为运行时 API。

## 3. 不可破坏的不变量

任何后续方案必须证明：

1. Workspace 隔离不变，不能跨 Workspace 解析或跳转 locator。
2. 已保存的历史 citation 在重索引、parser 升级或 chunk 替换后含义不变。
3. `citationIndex` 仍按单条 assistant message 从 0 开始，正文 `[n]` 映射不变。
4. citation 转 note 仍只接受当前 Workspace 的真实 citation，并复制不可变来源快照。
5. 文档删除后，历史回答和 note source 仍可显示标题、摘要和定位快照；源文件不可用时 Viewer 明确显示源已删除。
6. 重索引只替换可重建投影，不能原位改写已保存 Evidence 的含义。
7. 运行时缩放、滚动、焦点和面板状态不进入持久化 locator。
8. 聚合、数量和分布问题走结构化分析路径，不能让 LLM 根据少量召回结果猜总量。

## 4. 目标职责边界

以下职责已经批准并在 Phase 1 落地：

- `Asset`：Workspace 归属、权限、生命周期、源对象身份和类型。
- `Representation`：原 PDF、OCR、页面布局、表格结构、caption 等版本化派生物。
- `ContentUnit`：段落、区域、表格或图像等可寻址的检索/分析单元。
- `Embedding`：ContentUnit 的可重建索引投影，可存在多个 provider/model/version。
- `EvidenceLocator`：带 discriminator 和版本的稳定源定位值。
- `Citation`：回答生成时冻结 locator、展示快照和索引语义的证据记录。

`Document/Page/Chunk` 已由 Asset/Representation/ContentUnit/Embedding 一次受控迁移取代，没有保留长期双模型业务层。Image Phase 3 闭环已经完成，M403B 进一步启用了 PNG/JPEG/WebP 生产摄取入口。

## 5. Locator 提案

### 5.1 `pdf_page`

```json
{
  "kind": "pdf_page",
  "version": 1,
  "pageNumber": 8
}
```

规则：

- `pageNumber` 从 1 开始。
- 它表达整页证据，语义等同当前 `pageNumber` citation。
- 旧 citation 迁移时只能机械映射为 `pdf_page`，不能推断不存在的区域。

### 5.2 `pdf_region`

```json
{
  "kind": "pdf_region",
  "version": 1,
  "pageNumber": 8,
  "coordinateSpace": "pdf_crop_box_normalized_top_left_v1",
  "pageGeometry": {
    "cropBoxPoints": [0, 0, 612, 792],
    "rotationDegrees": 0,
    "displayWidthPoints": 612,
    "displayHeightPoints": 792
  },
  "regions": [
    { "x": 0.12, "y": 0.31, "width": 0.48, "height": 0.08 }
  ]
}
```

提议规则：

- 坐标相对应用页面旋转后的 CropBox 显示空间归一化，原点在左上角，x 向右、y 向下。
- `x/y/width/height` 范围为 `0..1`，且区域必须落在页面内。
- `pageGeometry` 是生成 citation 时的快照，用于检查 parser/Viewer 对同一页的几何解释是否一致。
- v1 的多个 `regions` 必须位于同一页，按阅读顺序排列，语义是共同支持同一条 citation 的区域集合。
- 跨页证据使用多条 citation，不在一个 locator 中混合多个页。
- OCR pixmap 已应用 CropBox 和 rotation，bbox 直接按实际 pixmap 宽高归一化，不再次旋转；原生 layout bbox 才使用 `rotation_matrix` 转到显示空间。该规则已由非对称 CropBox、0/90/180/270 旋转和真实扫描 OCR fixture 验证。

### 5.3 `image_region`

```json
{
  "kind": "image_region",
  "version": 1,
  "coordinateSpace": "image_normalized_top_left_v1",
  "widthPixels": 2400,
  "heightPixels": 1600,
  "orientationApplied": true,
  "regions": [
    { "x": 0.18, "y": 0.2, "width": 0.42, "height": 0.3 }
  ]
}
```

已批准并实现的规则：

- 图片在生成 Representation 时应用 EXIF orientation，locator 针对已定向显示空间。
- 坐标归一化到完整图片，原点左上，x 向右、y 向下。
- 整图证据使用覆盖全图的 region，不伪造 `pageNumber=1`。
- 多区域属于同一图片，按阅读/支持顺序排列并联合支持同一 citation。

## 6. Citation 快照提案

区域级 citation 仍需要保留：

- citation ID、message ID 和 `citationIndex`
- Workspace 和源资产关联
- locator kind/version 与完整定位快照
- document title 和 excerpt 快照
- 生成时使用的 representation/parser/index 版本
- 可选 ContentUnit 关联；关联失效不能让历史 citation 无法显示

`NoteSource` 已复制 locator、展示快照与 sourceVersions，而不是只保留对 citation 的外键；对应列和 API 字段已在 Phase 1 落地。

## 7. 持久化选项

### 选项 A：统一 locator 头 + 模态专用扩展表，推荐进入实施设计

- `evidence_locators` 保存 Asset、kind/version 和处理版本公共快照。
- PDF/Image 的几何存入类型化 detail 与 region 表，字段可约束和查询。
- Citation、NoteSource 和 ContentUnit 关联独立 immutable locator row，不重复模态列。
- 后续音频/视频增加 temporal detail/range 表，不修改 Citation/NoteSource 核心结构，也不把所有模态塞进任意 JSON。

优点：PDF/Image 约束清楚，数据库可验证，历史迁移可机械证明；未来模态不改核心快照表。缺点：每种新 locator 仍需要明确 schema、codec、migration 和 fixture，这是有意的质量门禁。

### 选项 B：带 discriminator 的通用 JSONB locator

- citation 保存 `locator_kind / locator_version / locator_payload`。
- 应用层使用 discriminated schema 校验 payload。

优点：扩展快。缺点：数据库约束弱，容易把模态业务规则堆进共享代码；当前不推荐直接采用。

### 选项 C：迁移 Asset/Representation/ContentUnit/Embedding 模型

V3 推荐。独立图片需要真实资产生命周期、派生表示、检索单元和 Evidence，继续把图片塞进 Document 或另建平行业务模型会制造长期边界债务。迁移必须受控完成，不能边猜字段边双模型运行。

## 8. API 实施门禁

Phase 1 已按以下门禁完成受控切换：

- 当前 Citation/NoteSource payload 与候选新 payload 的并列 fixture。
- Chat 历史、Chat SSE、citation 点击和 note source 的版本策略。
- 旧客户端遇到 `pdf_region/image_region` 时的明确行为；不能静默丢区域或猜字段。
- OpenAPI schema 和前后端 discriminated union 类型。
- 删除源文件、缺失 ContentUnit、parser 升级和重索引后的回放结果。

批准范围不包含长期兼容层。当前 API 使用 Asset、`assetScope` 和 discriminated locator union，未知 locator version 必须 fail-closed。

迁移前与候选 payload 的历史评审对照位于 `docs/fixtures/evidence-contract/`。文件名含 `.draft` 或 payload 包含旧 `contractStatus` 的文件仍只保存评审来源，不是运行时 schema；生产合同以 Pydantic DTO、OpenAPI 和已批准坐标 manifest 为准。

迁移、不可逆 downgrade、历史回放、删除/重索引和备份恢复影响见 `docs/architecture/evidence-migration-impact.md`。Phase 2-4 继续按 V3 spec 的阶段门禁推进。

## 9. 评测与运行证据

合同实施至少需要以下 fixture：

- 无旋转、90/180/270 度旋转 PDF 页面。
- MediaBox 与 CropBox 不同的页面。
- 原生文本 PDF、扫描 PDF、表格、图表和多区域证据。
- EXIF 旋转、不同宽高比、OCR 文本、整图和多区域图片证据。
- 旧 `pageNumber` citation 与 note source 回放。
- 源文档删除、重索引和 parser 版本升级。
- 桌面与移动 Viewer 在不同缩放下的同一区域高亮像素对比。
- 备份后销卷恢复，locator 和历史来源快照保持一致。

## 10. 已批准决策

以下六项已由用户明确批准：

1. 是否接受从 Document 领域迁移到 Asset/Representation/ContentUnit/Embedding 目标结构。
2. 是否接受 `pdf_page/pdf_region/image_region` 及两个 normalized top-left 坐标定义。
3. 是否接受多区域限制为同一页或同一图片、有序、联合支持语义。
4. 是否接受统一 immutable locator 头、模态类型化扩展表和封闭注册协议，不采用通用 JSONB。
5. 是否接受 Chat `assetScope`、消息范围快照与 Asset/Citation/NoteSource 新 API 版本的一次受控切换。
6. 是否接受旧 citation 只机械迁移为 `pdf_page`，以及源删除后只保留快照、不再打开 Viewer。

批准范围允许一次受控切换持久化、API、SSE、Worker 与 Web 合同；不允许引入 Document/Asset 长期双模型或推断历史区域。
