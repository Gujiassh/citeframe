# V3 多模态工作区交互设计

## 1. 设计状态

- 范围：多模态 PDF + 独立图片 Asset
- 状态：目标设计，待 Evidence 数据/API 合同批准后实施
- 不包含：音频、视频、Omnilabel、任意文件预览器
- 延期门禁：真实用户任务验证保留为 Beta 验收项，不阻塞内部工程实现

## 2. 核心产品裁决

Chat 继续是默认主画布，右侧不再是固定的 PDF 阅读器，而是按 citation、资产或用户选择打开的 `Evidence Viewer`。左侧从“PDF 文档列表”升级为“资产列表”，但 Workspace、Chat、Notes 和 Settings 的主导航不重做。

V3 的完整主链是：

`上传 PDF/图片 -> 处理为可检索证据 -> 选择提问范围 -> Chat 回答 -> 打开页/区域 citation -> 核验 -> 保存带定位快照的笔记`

不能先做一个只改名称、仍以 `documentId + pageNumber` 驱动的多模态壳。图片必须拥有真实上传、处理、检索、citation、Viewer 和 NoteSource 闭环后才在界面出现。

## 3. 工作区信息架构

### 3.1 左侧资产栏

左侧保留现有 Workspace 与线程管理，在知识来源区域做以下调整：

- 标题从“文档”改为“资产”。
- 使用 `全部 / PDF / 图片` 分段筛选，不增加音频或视频禁用入口。
- 上传使用一个上传图标按钮和类型菜单；只允许 PDF、PNG、JPEG、WebP。
- 每个资产行显示类型图标、文件名、处理状态和标签；不嵌套第二层卡片。
- 资产行单击打开 Evidence Viewer；复选框只控制 Chat 证据范围，不承担打开动作。
- Chat 范围默认是当前 Workspace 中全部 `ready` 资产。用户显式勾选后切换为选中资产集合。
- 处理中、失败或删除中的资产不能进入提问范围；失败行提供重试命令。

资产状态统一显示为用户可理解的阶段：`上传中 / 解析中 / 建索引 / 可用 / 失败 / 删除中`。后台可以有不同 job 类型，但界面不展示内部枚举。

### 3.2 Chat 主画布

Chat 主画布结构保持稳定，只增加紧邻输入框的证据范围条：

- 未限制时显示“全部资产”和可用资产数量。
- 有显式选择时显示 PDF/图片图标与最多两个资产名，其余折叠为数量。
- 清除范围使用 `X` 图标，资产选择使用菜单或左侧复选框。
- 发送请求时使用 `all_ready | selected` scope；服务端把当时实际参与检索的资产集合保存为消息范围快照，后续上传、删除或改变选择不能改写历史消息语义。
- 回答中的 citation 继续使用稳定编号 `[n]`，但来源行按 locator 显示 `PDF p.8`、`PDF p.8 · 图表` 或 `图片 · 区域`。

不在 Chat 中增加模型名称、检索管线说明或多模态功能教学文案。

### 3.3 Evidence Viewer

Evidence Viewer 复用当前右侧可拖拽调宽、移动端覆盖和全宽阅读模式，内部按资产类型选择 renderer：

```text
EvidenceViewer
├─ EvidenceHeader
│  ├─ 资产类型、标题、定位摘要
│  └─ 适应窗口、全屏、关闭
├─ PdfEvidenceRenderer
│  ├─ 页码、缩放、目录/缩略图
│  └─ 文本层、OCR 层、region overlay
└─ ImageEvidenceRenderer
   ├─ 适应窗口、1:1、缩放、平移
   └─ region overlay
```

Viewer shell 只负责标题、来源可用性、宽度、全屏、关闭、错误边界和响应式行为。具体 renderer 由构建期 `EvidenceModule` 注册表按经过 schema 校验的 locator kind 调度；后续音频/视频增加 renderer 时不修改工作区页面、Chat 或 Viewer shell。

PDF renderer：

- 保留页码输入、目录、缩放、原生文本层、OCR 选择层和 annotation layer。
- `pdf_page` 打开指定页，不显示伪造区域。
- `pdf_region` 打开指定页并高亮一个或多个区域；高亮随缩放和旋转变换，不改变 locator。
- 用户手动翻页后保留 Viewer 打开状态，但 citation 的定位摘要不被改写。

图片 renderer：

- 图片以完整内容为第一视觉信号，不做模糊背景或装饰性裁切。
- 支持适应窗口、100%、缩放、平移和区域高亮。
- citation 打开时将目标区域置于可见范围；若区域已在视口内，不强制重新居中。
- 不提供 PDF 页码、目录或文本层控件。

### 3.4 Citation 与笔记

- Citation 点击必须根据 locator kind 打开正确 renderer，不能通过 MIME 猜测定位语义。
- Citation 来源行保留标题和 excerpt；图片 citation 的 excerpt 使用生成时冻结的区域描述或 OCR 文本。
- 从 citation 创建 Note 时复制 locator、标题、excerpt 和版本快照。
- Note 来源点击使用其自身快照定位，不能重新读取当前 Citation 覆盖历史来源。
- 源资产删除后仍显示来源标题、类型、定位摘要和 excerpt；Viewer 显示“源资产已删除”，不尝试打开其他同名文件。

## 4. 选择与反馈

### 4.1 PDF 选择

- 文本选择继续提供“提问”和“记笔记”。
- OCR 文本选择使用 OCR block 的坐标生成候选区域。
- 表格、图表或图片区域选择采用框选工具；框选只在用户主动进入选择模式后启用，避免干扰滚动与文本选择。

### 4.2 图片选择

- 图片默认是平移/缩放模式。
- 用户切换到框选模式后拖出一个归一化区域，再选择“提问”或“记笔记”。
- `Escape` 取消未提交框选；框选取消必须先消费该按键，不能同时关闭 Evidence Viewer；完成动作后回到平移模式。
- 历史 M304A 阶段只实现框选草稿；M304B 批准后已接通“提问”和“记笔记”动作。区域仍不能序列化成 `selectionText`，也不能在没有 Citation 的情况下伪造 NoteSource。

### 4.3 状态反馈

- 上传与处理过程保留稳定行高，进度和状态变化不能推动其他资产跳动。
- citation 打开时先立即切换资产与定位语义，再加载显示资源；不能让图片下载或 PDF 渲染延迟业务选择状态。
- region 几何与当前 representation 不匹配时明确显示“定位版本不一致”，不静默降为整页或整图。
- 动画只用于面板进入、renderer 切换和定位高亮，持续时间控制在 150-300ms，并遵守 `prefers-reduced-motion`。

## 5. 响应式行为

### Desktop

- 左侧资产栏、Chat 主画布、Evidence Viewer 三列并存。
- Evidence Viewer 可拖拽调宽，Chat 保持可用最小宽度。
- 全宽阅读模式覆盖工作区，不嵌入额外卡片。

### Tablet

- 左侧资产栏与 Evidence Viewer 均为可关闭抽屉，同一时刻只覆盖一侧。
- Chat 保持主画布，不因资产类型增加横向滚动。

### Mobile

- 默认只显示 Chat。
- 资产列表和 Evidence Viewer 分别使用全屏层，顶部提供明确返回按钮。
- Viewer 工具栏使用图标与 tooltip，触控目标不小于 44px。

## 6. 运行时状态边界

以下状态只属于 Web runtime，不进入 Asset、Citation 或 NoteSource：

- 当前打开的资产和多个临时页签
- Viewer 宽度、是否全屏、缩放、滚动和平移位置
- 当前 PDF 页（除非由 locator 打开）
- 当前框选草稿和选择工具模式
- 左侧资产筛选、展开状态和 Chat 输入框临时范围

以下语义必须持久化或随消息请求冻结：

- 问题的范围模式与实际使用的资产快照
- 用户消息显式提交的输入 Evidence，包括服务端解析后的 locator、excerpt 与 sourceVersions；历史输入只用于展示和定位，不隐式重发给模型
- Citation/NoteSource 的 asset、locator、标题、excerpt 和版本快照
- Asset 类型、源对象身份、处理/representation 版本
- ContentUnit 与 embedding 的来源版本

## 7. 验收场景

1. 上传一个 PDF 和一张图片，两者均完成处理并进入同一 Workspace 检索。
2. 问题限定到图片时，网络请求和回答 citation 不包含未选 PDF。
3. PDF 图表 citation 打开指定页和区域；缩放后高亮仍对齐。
4. 图片区域 citation 打开原图并高亮指定区域；100% 与适应窗口模式定位一致。
5. Citation 转 Note 后删除源资产，历史回答和 NoteSource 仍显示冻结快照。
6. 刷新历史 Chat 后 citation 编号、类型和 locator 不变。
7. 桌面、平板、手机均能完成 `提问 -> 打开证据 -> 返回 Chat`，无重叠或横向溢出。
