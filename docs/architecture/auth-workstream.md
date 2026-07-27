# 认证工作流任务清单

> 文档状态：历史执行工作流。认证、membership、BFF session、notes/tags 和内部 token 已完成；当前实现事实以 `docs/architecture/implementation-progress.md`、`docs/ssot/system-architecture.md` 和代码测试为准。本文的“当前执行到模块 2”只表示当时的阶段记录，不是未完成任务。

## 1. 目标

本工作流负责把早期 `mock 登录 + 本地工作区沙盒` 替换为正式认证链。当前原则是：mock 只保留 UI 壳，不再保留旧 mock 逻辑作为兼容目标。

当前按模块推进，避免一次把登录、数据库、membership、BFF 全部卷在一起。

## 2. 模块拆分

### 模块 1：开发模式最小登录/注册

目标：

- 支持显式注册
- 支持显式登录
- 支持本地 session 持久化
- 登录不自动注册

边界：

- 实现真实 FastAPI 注册/登录接口
- 通过 Next.js BFF 接入登录、注册、登出、session cookie
- 不做 workspace membership
- 不做页面级权限守卫

完成标准：

- 用户未注册时不能登录
- 用户可手动注册新账号
- 注册成功后不会自动登录
- 用户登录后 BFF 通过 httpOnly cookie 保存 7 天 session
- 用户刷新页面后仍能保持登录态
- 退出登录后 session 被清理

### 模块 2：Workspace membership 真数据链

目标：

- 用真实用户上下文替换当前匿名工作区数据
- 按当前用户 membership 返回可见工作区

边界：

- 接入 `users / workspaces / workspace_memberships`
- 替换 `/api/workspaces` 和 `/v1/workspaces` 的 mock 数据

### 模块 3：真实 session / BFF 上下文

目标：

- 用正式 session 替换开发模式本地 session
- 让 BFF 带着真实用户上下文访问 FastAPI

边界：

- 接入 Auth.js 或等价方案
- 让页面与 BFF 使用统一 session 获取入口

### 模块 4：权限守卫与页面保护

目标：

- 未登录用户不能进入工作区页
- 无 membership 的用户不能访问不属于自己的 workspace

边界：

- 页面保护
- BFF 保护
- API 侧 workspace 校验

## 3. 当前执行策略

历史执行记录（2026-07-08）：`模块 2：Workspace membership 真数据链（第一段）`

当前状态：
- 模块 1 已完成真实后端认证接入（register/login/logout/session），并已从前端 workspace mock 状态中拆出独立 auth context
- BFF session 现已要求显式配置 `AI_PDF_SESSION_SECRET`，cookie 的 `secure` 将随 `NODE_ENV` 自动切换
- 已补 FastAPI auth 接口自动化测试：覆盖注册成功、重复注册、正确登录、错误密码四个基本行为
- 模块 2 第一段已完成：`users / workspaces / workspace_memberships` 最小真表链路已接通，`/api/workspaces` 与 `/v1/workspaces` 已改为按当前登录用户 membership 返回列表/详情，并支持创建和 owner 归档
- 当前主工作台里的 notes / tags 已切到真实表、API、BFF 和前端恢复链路；citation -> note 会校验当前 workspace 的 `message_citations` 并保存来源快照，旧 notes/tags localStorage/mock 数据流已删除。threads 同样使用真实表、API、BFF 和前端恢复链路。
- 模块 3 已通过等价的 BFF httpOnly session 方案完成；业务 API 额外要求 `x-ai-pdf-internal-token`，模块 4 的生产级页面守卫和正式 IAM 仍可后续增强


## 2026-07-15 内部调用边界

FastAPI 业务路由统一由 `require_user_id` 同时校验 `x-user-id` 和 `x-ai-pdf-internal-token`。token 只在 Web/API 服务端环境变量 `AI_PDF_API_INTERNAL_TOKEN` 中配置；BFF 通过 `buildApiHeaders()` 统一注入，避免各 route 手写鉴权 header。
