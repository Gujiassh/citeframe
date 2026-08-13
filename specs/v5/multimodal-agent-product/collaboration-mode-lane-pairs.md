# 合作模式：主控集成 + 分车道双人制

Date: 2026-08-13  
Status: **approved as operating mode**（先手动执行，不先做调度产品）  
Applies to: Citeframe 及同类多线开发  
Parent: [`current-execution-plan.md`](current-execution-plan.md)

## 1. 模式名称

**中文：** 主控集成 + 分车道双人制（实现 / 独立审计）  

**英文（并列，不是单一商标）：**

- Lane-based development  
- Hub-and-spoke / Integration owner  
- Implementer + independent reviewer per lane  
- 与仓库 `AGENTS.md` 的 Main Controller + Subagent 同一类，并固定「每线一对开发/审计」

## 2. 一句话

主控按波次拆线；每条线一个隔离工作区，配一名开发和一名审计；线内搞完提 MR；主控终审合入主干、删除旧分支，再派下一波。

## 3. 协作闭环

```text
主控（你 / 本会话主控）
  ├─ 分波次、分工作区、写派工单（文件边界 + 验收 + 禁止改动）
  ├─ 工作区 L1：开发 ──→ 审计 ──→ MR
  ├─ 工作区 L2：开发 ──→ 审计 ──→ MR
  └─ …
        ↓
  主控再审 MR → 合进主干 → 删本地/远端旧分支与多余 worktree
        ↓
  主控再分下一波
```

### 角色

| 角色 | 职责 | 禁止 |
|---|---|---|
| **主控** | 拆线、指定工作区、终审 MR、合入、删分支、再派活 | 不要和一线开发抢改同一文件集 |
| **开发** | 在本工作区实现本线，自测，开 MR | 不改其它线文件；不绕过审计直接找主控合入（除非主控明示） |
| **审计** | 独立审 diff/测试/合同/SSoT；打回原开发 | 不兼任本线开发；不扩 scope；不另开第三人改同一文件除非开发不可用 |

### 波次

- 同一波内多线 **并行**（文件集不重叠）。  
- **S0 共享内核**（registry / OpenAPI union / retrieval / 同一 alembic 队列）**串行合入**，由主控或指定 S0 owner。  
- 一波全部合入（或明确砍线）后，再开下一波。

## 4. 工作区与 Git 约定

| 项 | 约定 |
|---|---|
| 隔离 | 每线一个 git worktree / 工作区（本模式视为主控批准的多 worktree **例外**） |
| 分支 | `work/<lane>-<yyyymmdd>` 或等价；从当前主干 HEAD 拉出 |
| 目标 | MR 合入 `main`（或当时约定的集成分支，Citeframe 现为 `main`） |
| 合入后 | 删远端分支、删本地分支、移除已无用 worktree |
| 身份 | 合入前检查 remote 与 git user（仓库规则） |
| 提交说明 | Citeframe：**英文** commit；不擅自 push 除非本轮允许 |

### 派工单最低字段

每线开工必须有书面 brief（可放 workbench / `docs/evals/...` / MR 描述）：

- lane id、目标、非目标  
- 允许/禁止路径  
- 合同影响（无 / 需 checklist）  
- 验收命令  
- 开发 owner、审计 owner  
- 源 SHA / 主干 ref  

## 5. MR 与审计标准

线内审计 + 主控终审都按仓库 Review Defaults，至少：

1. 目标对齐（有没有漂成兼容层/临时结构）  
2. 架构边界（S0 有没有被一线擅自改）  
3. 数据/保存合同  
4. 测试与证据  
5. SSoT/规格是否同步  

主控 **不信任** 线内审计口头「过了」；必须看 diff + 关键验证再合。

打回：优先 `resume` 原开发；不要新开第三人覆盖同一文件。


## 5.1 Agent 复用（省 token）

- **同一条线的返工、追问、补测、改 PR：必须 `resume` 原开发 / 原审计。**
- **禁止**因为「新开一轮对话」就再 spawn 一个实现或审计 agent。
- 只有这些情况才新开：原 agent 会话不可用、lane 范围已变、需要独立第二审、或主控明确换人。
- 新开时必须在派工单写明 **为什么不能 resume**。
- **审计 agent 默认用 Grok（grok-4.5）**，不要用 GPT；实现 agent 另议。上游卡顿时优先保审计走 Grok。

## 6. 工具策略

**默认纯手动，不先开发调度产品。**

手动即可：

- `git worktree add`  
- 主控 spawn 开发 / 只读审计 subagent  
- GitHub/GitLab MR  
- merge 后删分支、拆 worktree  

以后若重复劳动再考虑薄脚本（建线、列可删 worktree），**不是**本模式的前置。

## 7. 与 Citeframe 当前计划的套用

开工后（现仍 **O5 先不开工**）第一波建议：

| 工作区 | 开发 | 审计 | 范围 |
|---|---|---|---|
| pdf-visual | 实现 | 独立审 | `pdf-in-page-visual-v1.md` |
| html | 实现 | 独立审 | V5-F HTML |
| office | 实现 | 独立审 | docx→xlsx→pptx 或再拆工作区 |
| asr | 实现 | 独立审 | F-ASR |

S0 合入与终审：主控。  
W1 合完再派 Audio/Video / MIX。

## 8. 非目标

- 不做成通用「多智能体操作系统」产品  
- 不取消线内审计、不改成主控一人兼开发多线同一文件  
- 不把 accept stub 环境当 preview  

## 9. 相关文档

- [`current-execution-plan.md`](current-execution-plan.md)  
- [`parallel-execution-plan-v5f.md`](parallel-execution-plan-v5f.md)  
- [`docs/architecture/local-env-profiles.md`](../../../docs/architecture/local-env-profiles.md)  
- 仓库根 `AGENTS.md`：Main Controller + Subagent  
