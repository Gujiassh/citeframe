# Web App (Citeframe 前端)

本模块是基于 Next.js App Router 构建的高阶 PDF 研究协同工作台前端应用。

## 1. 当前实施状态 (Current Implementation State)

目前核心数据链路已接通：`workspace`、`documents`、Chat thread/message/citation、notes、tags、Workspace settings 及其 BFF/API 均已接入真实数据；旧 mock 数据流不再作为兼容目标继续维护。

* **已落地功能 (Implemented)**：
  * **工作区大盘门户 (`/`)**：100% 宽度极简 SaaS 表格行布局，支持开发模式下的显式注册、显式登录与工作区隔离删除。
  * **三栏分屏控制台 (`/workspaces/[workspaceId]`)**：嵌入式分屏协同工作台，中栏 PDF 浏览器与右侧 Copilot 多面板联动。
  * **原始 PDF 阅读**：通过受权限保护的文件流读取源 PDF，PDF.js canvas 保留图片与排版；原生文本 PDF 叠加 text layer，PDF 内置链接/批注使用 annotation layer。
  * **物理解耦组件群**：
    * `OutlineTree`：树形大纲折叠导航。
    * `SelectionPopover`：精确定位划词 AI 问答/记录笔记浮层。
    * `ChatBubble`：AI 对话气泡与内嵌随手记编辑器。
    * `CreateWorkspaceDialog`：工作区创建 Modal 对话框。
  * **真实知识沉淀**：Notes 使用真实 CRUD、来源快照和 workspace 隔离；Tags 使用真实 CRUD，并支持 document/note 多对多绑定与筛选。
  * **真实 Workspace 设置**：系统提示词、检索 top-k、入库 chunk size 通过 BFF/API 持久化；provider/model/dimensions 只读展示服务端运行配置。
  * **BFF 内部边界**：服务端请求使用 `AI_PDF_API_INTERNAL_TOKEN` 注入 `x-ai-pdf-internal-token`，浏览器不会接触该 token。
  * **多语言与暗黑模式**：内嵌统一的 `i18n-context` 与 `theme-context`。
  * **响应式定位抽屉**：手机/平板等宽幅下自动绝对化浮动（`absolute z-40`）并带有遮罩蒙层。
* **规划目标态 (Target to Implement)**：
  * 后续按部署、日志与观测切片完善运行保障。
  * 继续保持 citation -> note 的真实 `message_citations` 来源快照回归覆盖。

说明：Worker 生成的 `document_pages` / `document_chunks` / OCR 文本用于检索与 citation，不会替代 Viewer 中的原始 PDF 页面。

## 2. 运行与编译 (Development)

### 在仓库根目录运行

首次启动先创建本地 BFF 环境文件：

```bash
cp apps/web/.env.example apps/web/.env.local
```

将 `AI_PDF_API_INTERNAL_TOKEN` 与 API 环境保持一致，并把
`AI_PDF_SESSION_SECRET` 替换为仅保存在本机的长随机值。缺少 session secret 时登录
会 fail closed，BFF 不会签发 cookie。

启动 Web 开发服务器：
```bash
pnpm dev
```

构建 Web：
```bash
pnpm build:web
```

### 在 `apps/web` 目录内单独运行

启动开发服务器：
```bash
pnpm dev
```

构建生产版本：
```bash
pnpm build
```

`predev` 和 `prebuild` 会从已安装的 `pdfjs-dist` 自动复制浏览器端 PDF.js 主文件、worker 和 annotation 图标到 `public/pdfjs/`；这些生成文件不作为源码维护。

## 测试与浏览器 smoke

```bash
pnpm test
pnpm lint
pnpm exec tsc --noEmit
pnpm exec playwright install chromium
PLAYWRIGHT_START_WEB=1 pnpm e2e
```

默认 Playwright smoke 会验证未登录入口；设置 `PLAYWRIGHT_E2E_EMAIL`、`PLAYWRIGHT_E2E_PASSWORD` 后会额外验证登录、创建 Workspace 和 settings 持久化。再设置 `PLAYWRIGHT_E2E_PDF_PATH`，并准备可用的 API、数据库、MinIO、Worker 和模型 provider，才会执行 PDF canvas、OCR 选区、流式问答和编辑分支回归。设置 `PLAYWRIGHT_E2E_IMAGE_WORKSPACE_ID` 与 `PLAYWRIGHT_E2E_IMAGE_ASSET_ID` 后，还会对该 ready Image Asset 执行 current generation 409 恢复、单指触控平移和 Escape 只取消框选草稿的回归。
