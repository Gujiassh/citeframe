# V5 Save / API / Schema Contract Checklist

## 使用时机

任何 V5-B/V5-C worker 发现需要以下任一改动，必须停止实现并向 main controller 报告：

- 新增/删除/重命名数据库列、表、catalog literal 或 enum meaning；
- 改变 Asset status、generation、index、delete、retry、restore 语义；
- 改变 Citation、NoteSource、Chat message、Chat SSE 或 Research ledger 保存字段/顺序/快照；
- 新增 provider selector、Workspace profile selector、动态 Agent step/tool；
- 改变 EvidenceLocator literal、detail family、coordinate/time/path semantics；
- 改变权限、预算、provider secret、cost 或数据边界。

不得用 compatibility layer、fallback chain、静默 coercion 或双写来绕开审批。

## 1. 影响说明模板

```text
Change ID:
Owner lane:
Requested behavior:
Why existing contract is insufficient:
Affected tables/columns/catalog rows:
Affected API DTO/OpenAPI/SSE:
Affected old payload/save semantics:
Affected Citation/NoteSource/Chat/Research history:
Migration direction and rollback:
Backup/restore format impact:
Permission/Workspace impact:
Provider/cost/secret impact:
Required fixtures and old/new comparison:
Required reviewer class: Standard | Critical
Decision document:
Approval owner/date:
```

## 2. Must-preserve oracle

### Citation / NoteSource

- Citation index and message body mapping unchanged。
- Citation stores immutable Asset/title/excerpt/sourceVersions/locator snapshot。
- NoteSource clones an independent locator and does not depend on current derived rows。
- Deleted source leaves historical snapshot readable with `sourceAvailable=false`。
- Reprocess/reindex never rewrites historical locator or excerpt meaning。

### Chat

- Quick Chat remains separate from Research Run ledger。
- `assetScope` validation and actual scope snapshot unchanged。
- Existing SSE event shape and old public error shape unchanged unless separately approved。
- Embedding/index mismatch does not half-save messages or silently return a successful answer。

### Research

- Approved execution snapshot is the only runtime provider/asset/budget truth。
- Proposed plan display may use proposed snapshot only under the existing precedence rule。
- PostgreSQL remains business truth; MinIO remains immutable artifact bytes。
- Decision/retry/cancel mutations require authorization, idempotency and expected state version。
- Claim/Evidence publication cannot promote unsupported/conflicted claims to facts。

## 3. Required comparison evidence

For Critical changes, compare old/new fixtures or payloads for:

1. historical Chat response and citation DTO；
2. Citation -> NoteSource cloned payload；
3. before/after reindex and reprocess snapshots；
4. source delete and historical read；
5. Research plan/execution/artifact/claim/evidence payload；
6. backup/restore row/object checksums when tables or objects change；
7. old PDF/Image mixed workspace behavior。

## 4. Approval stop rule

没有明确批准前，worker 只能：

- 添加失败测试证明缺口；
- 添加 draft fixture/spec；
- 输出影响说明和最小方案；
- 不修改生产 contract、migration 或 save path。
