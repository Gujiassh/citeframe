# R500 Web Research Run 体验验证

日期：2026-07-27

状态：`engineering_web_gate_passed`

本报告只证明 Web/BFF 的 R500 工程体验和客户端 Research SSE 合同。浏览器用例使用获批
camelCase DTO 的同源 mock，不证明真实 provider 质量、API/Worker 重启恢复、PostgreSQL 账本恢复或
M404 用户价值；这些门禁仍须由 R400/R800 和真实用户证据分别关闭。

## 1. 语义 oracle

| Oracle | 结果 | 证据 |
| --- | --- | --- |
| Quick 是初始默认模式 | pass | desktop/mobile 首屏均断言 Quick tab `aria-selected=true` |
| Research 必须显式选择 | pass | 只有点击 Research tab 后才出现 Research composer 和运行视图 |
| Quick 继续依赖 Chat thread | pass | 无 thread fixture 中 Quick composer 保持 disabled |
| Research 不依赖 Chat thread | pass | 同一无 thread fixture 可创建 Research Run |
| Quick Chat 合同不承载 Research | pass | Research 使用独立 BFF、client、hook 和 SSE parser；未修改 Chat request/SSE 事件 |
| Research mutation 使用幂等键 | pass | Playwright 捕获 create/approve 的非空 `Idempotency-Key` |
| 历史运行选择不依赖返回顺序 | pass | 单测按 `createdAt`、再按 `id` 确定最新运行 |
| 创建者动作不泄露给 reader | pass | reader 浏览器用例不渲染 approve/revise/cancel；Hook 同样 fail closed |
| Plan 决策信息完整 | pass | desktop/mobile 展示 frozen scope、known gaps、预计 provider calls 与 cost |
| Conflict 绑定 immutable Artifact | pass | 只有 `id/sha256/kind` 精确匹配 pending Decision 的 `conflict_report` 加载完成后才显示裁决动作 |
| Asset scope 显式且稳定 | pass | 未选择 Asset 时 create payload 精确为 `{mode: "all_ready"}` |
| SSE 只接受批准的事件合同 | pass | exact 15-event allowlist、decimal seq、逐事件 exact data fields、无 gap、同 Run 校验 |
| 410 不伪装成完整 replay | pass | 单测恢复当前 snapshot 后进入 `history_unavailable` 状态 |
| Artifact Evidence 不扩张 locator | pass | `pdf_page` fixture 通过，候选 `audio_range` 在打开 Viewer 前 fail closed |
| BFF header 最小化 | pass | SSE、JSON mutation、Artifact content 分别使用端点级 request/response allowlist |
| desktop/mobile 无页面横向溢出 | pass | Playwright 断言 `scrollWidth - clientWidth <= 0` |

## 2. 实现手段

1. 在 Chat composer 上方增加 Quick/Research segmented control；Research 提交走独立
   `/api/workspaces/{workspaceId}/research-runs`，不要求 Chat thread。
2. 新增同源 Research BFF，原样转发状态码，并按 SSE、JSON mutation、Artifact content/read
   分别执行最小 header allowlist；浏览器不能注入内部认证或把 SSE cursor 带入普通请求。浏览器断开通过
   `request.signal` 传给上游。
3. 新增 Research client、DTO、hook 和独立 SSE parser。SSE 使用 per-run decimal seq，重复交付去重，
   gap 从最后连续 cursor 重连，未知事件、额外字段和跨 Run 事件 fail closed。
4. Research Run 视图以 `createdAt/id` 语义确定最新运行，展示 frozen Asset scope、known gaps、预计调用/成本、
   固定阶段、最终 Markdown、Viewer 跳转和脱敏 trace；creator 才能审批/修订/取消/重试/裁决。
5. 冲突操作先按 pending Decision 的 `inputArtifactId/inputArtifactSha256` 精确加载 `conflict_report` bytes 和
   normalized claims，`id/hash/kind` 任一不符都不开放操作。
6. Artifact Evidence 在进入 Viewer 前复用现有 PDF/Image locator 与 sourceVersions 运行时校验，
   不接受候选新模态 locator。

## 3. 调试与收敛记录

- 初次 lint 发现 effect 内同步重置表单和 stream state 会产生级联 render；改为按
  `workspaceId/runId/planVersion` 的组件 key 与派生状态隔离。
- 初次 Playwright 启动发现 `PLAYWRIGHT_BASE_URL` 可覆盖但 webServer 端口硬编码 3000；配置改为从
  base URL 派生 host/port。Next 16 同目录 dev lock 阻止第二实例后，没有终止现有 3000 服务，改用同工作树
  热更新实例完成验证。
- 初次 browser assertion 使用了错误的 Quick placeholder；根据 accessibility snapshot 改为稳定的 textbox
  accessible name，产品代码无需调整。
- 增加 creator 权限后，Playwright 暴露旧 session fixture 错用登录 DTO 的 `id`，而同源 session DTO 应为
  `userId`。修正 fixture 后 creator/reader 两条路径分别通过，避免用无效身份得到虚假的权限结论。
- 生产 standalone 首次验证只有 server 文件、缺少 `.next/static` 和 `public` 装配，页面无法 hydrate；按真实
  standalone 部署结构补齐静态资源后重跑 4 条用例，证明构建产物可用。
- 截图复审确认桌面与 390px mobile 中 header、模式选择、Plan、进度和 composer 无重叠；移动端保持单列信息流。
  最终截图来自 production standalone，不包含旧 Next dev server 的 Issues 浮层。

## 4. 验证结果

```text
git diff --check
pass

pnpm --filter @citeframe/web lint
pass

pnpm --filter @citeframe/web test
106 passed, 0 failed

pnpm --filter @citeframe/web build
pass; /api/workspaces/[workspaceId]/research-runs/[[...segments]] included

HOSTNAME=127.0.0.1 PORT=3001 node .next/standalone/apps/web/server.js
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001 \
  pnpm --filter @citeframe/web exec playwright test e2e/research-run.spec.ts --reporter=list
4 passed: creator desktop/mobile, reader permissions, Decision-bound conflict report
```

## 5. 浏览器证据

| Artifact | SHA-256 |
| --- | --- |
| `docs/evals/artifacts/r500-v1/r500-web-desktop.png` | `2ad517c7674f7edb1b5d70fa74d19082b96de391c0663762af37ab86805c3134` |
| `docs/evals/artifacts/r500-v1/r500-web-mobile.png` | `6e66b4bd19883f8d730443ebd79241442c9f20de907766e43c6674b7ee41501f` |

## 6. Review 判定

| Area | 判定 |
| --- | --- |
| Goal alignment | pass：Research 是显式可选流程，Quick 默认和 Chat 合同未漂移 |
| User-visible flow | pass：无 Chat thread 可提交 Research，Plan 冻结信息、creator-only HITL、冲突 claims、进度、错误和 Artifact 可见 |
| Architecture boundaries | pass：ChatPanel 只负责模式组合，Research client/hook/panel/SSE 分责 |
| Data/save contracts | pass：未修改 Asset、Citation、NoteSource、EvidenceLocator 或 Note save 语义 |
| Runtime identifiers/imports | pass：TypeScript 与 Next production build 通过 |
| Evolution | pass：阶段名和 locator 使用封闭映射，新模态不需要把业务判断塞进 Chat shell |

当前 Web 结构可进入 R400/R800 全栈集成。剩余风险是浏览器 fixture 未覆盖真实 API 长连接、API/Worker
重启、provider 生成的冲突 Artifact、真实失败分支 lease/retry 和最终 Artifact provenance；在这些证据完成前，不能把
R404/R800 或用户价值门标记为通过。
