# Issue42 index storage — independent Critical implementation review

日期：2026-09-29。

**结论：REQUEST CHANGES。IS01（P1）在 reviewer 自有 PostgreSQL17 上确定复现：REPEATABLE READ 旧快照可把已缺 chunk / 已变 pending 的 declared corpus 激活。原138项全过不能关闭此竞态。**

只退回原 owner 修复本次 table-local integrity 范围；既有 P1a/admission/history/image/HC02 接受和 IC01 设计批准保持。不要求重做 source/index 全链设计，也不把 native downstream obligations 当本候选已实现。

## 1. 目标、精确候选、接受 oracle

| 对象 | SHA-256 |
|---|---|
| packages/backend-persistence/src/citeframe_persistence/models/memory_index.py | ec63758e965f39bffdd7e36ec08dbc9f32bfa895c88c396d04d8a4b1d23d723a |
| packages/memory-service/tests/test_history_index_postgres.py | eea4224239b8f799d4d6dcb3c965961fc1a56efdc6ae93a897cfc453c4d95a2d |
| specs/v5/memory-management/evidence/issue42-index-storage.md | b17ca582bf141a4fba9cbf1cab2f7e4cd333b2ec09f278b4789af863174f6c66 |
| approved lanes/issue42-index-canonical-delta.md | 3e8a8f2f98917545df3bafe19b83869db6dec32ee0b27a8c9f32f49b71974625 |

开始与复验后 hash 一致。完整读取439行 model、840行 test 和 evidence；未改这些候选。

本轮目标是两个显式导入的新表能够严格保存 canonical source_set/profile，保持 workspace/source metadata 隔离，并在允许的直接 SQL 与并发下保证 **declared** source_set 的 profile/count/ordinal/range/readiness 完整性。原文是实际 native source 的精确 slice、完整 workspace corpus 枚举及当前 reader 许可仍由真实 owner/service 后续证明，不能由本 synthetic source fixture 代替。

## 2. IS01 — P1：锁串行化不刷新 REPEATABLE READ 的 entries 快照

**位置：memory_index.py:362–388 `memory_index_check_manifest`，:391–409 manifest lock/completeness triggers，:411–437 entry guard。**

`memory_index_entry_guard` 对 workspace/manifest 取得行锁，但 entry DELETE 或 state UPDATE 不修改 manifest 的 MVCC tuple。`memory_index_check_manifest` 的 entry 遍历（:366）及 count/min/max（:383–384）是普通快照读取。manifest 在激活时取得的 workspace 锁不会刷新 REPEATABLE READ 事务已经建立的快照，也不会因已提交的 entry 变更自动制造 manifest 行的 serialization conflict。当前没有 isolation-level fail-closed guard。

### 2.1 实际可提交反例

使用真实两个连接，先提交一份 declared chunk_count=1、实际有一条 lexical_ready entry 的 building manifest；source保持 current/public，所有 profile/hash 均有效。接着：

1. 连接A：`BEGIN ISOLATION LEVEL REPEATABLE READ`；SELECT entries count，读到1并建立旧快照。
2. 连接B：`DELETE FROM memory_index_entries WHERE manifest_id=:id`，经实际 entry trigger 后 **COMMIT**。
3. 连接A：`UPDATE memory_index_manifests SET state='active', activated_at=now() WHERE id=:id`，**COMMIT成功**。
4. 新连接观察：manifest=`active`，实际 entries count=`0`，违反自己声明的 chunk_count=1。

第二个反例将B替换为 `UPDATE ... SET state='pending'`；A同样成功提交，最终 `active` manifest 下保留 `pending` entry。原 active-entry DML guard不能阻挡这两条路径，因为B合法发生在 manifest 仍为 building 时。

独立实际输出：

```text
STALE_SNAPSHOT_DELETE READ COMMITTED before=1 result=IntegrityError:23514 committed=('building', 0)
STALE_SNAPSHOT_DELETE REPEATABLE READ before=1 result=ACTIVATED committed=('active', 0)
STALE_SNAPSHOT_PENDING READ COMMITTED 23514 ('building', 'pending')
STALE_SNAPSHOT_PENDING REPEATABLE READ ACTIVATED ('active', 'pending')
```

这是 index entries/manifest 自身的缺陷，不依赖 source mutation after activation、权限枚举、native deletion 或未来 migration。对照 READ COMMITTED 正确拒绝，使原9个默认隔离级别并发用例通过与本反例并不矛盾。

### 2.2 最小 owner rework 与关闭标准

在本两文件范围内选择明确的安全行为。较小修复是：**对依赖“当前集合”判定的 index mutating triggers 明确 fail closed 拒绝未支持的事务隔离级别，仅接受已证明正确的 READ COMMITTED 写入路径**，并用稳定无payload错误说明；不得仅在 pytest engine / future API 配置默认值。若要支持 REPEATABLE READ，则需要实际解决旧 entries 快照问题，不能再靠增加同类 workspace/manifest SELECT lock 宣称完成。不要为这个局部修复改 native表或引入新通用层。

至少加入上述两个精确双连接回归；A必须在B提交前取得 snapshot，最后由新连接验证 committed state。READ COMMITTED 正常正例/冲突用例、原9项并发、canonical/profile/source隔离和active-entry DML拒绝均保留。若采用有限隔离级别 admission，要覆盖 direct SQL，并对所有不支持模式（含 SERIALIZABLE 的明确取舍）验证失败而非跳过，确保完整 rollback；building profile/source-set变更的同类旧快照校验也应受该边界保护。

成功标准：不存在 `active + missing chunk` 或 `active + pending chunk` 的可提交状态。当前候选尚未达到；交回原 owner，而非 reviewer 代写产品。

## 3. 其它实物审查结果（不抵销 IS01）

| 方面 | 判定与证据 |
|---|---|
| IC01 canonical 两层 | pass at tested finite domain。Python strict int/bool-float拒绝，JSONB mathematical integral与范围检查分开；验证后canonical整数无小数/指数；C排序keys/UUID及UTF-8 compact bytes，无jsonb spaced hash替代 |
| source_set/profile shapes | pass。exact keys、source UUID/order/duplicates、4096/byte cap、版本/数值上限；profile固定数字、mode/space/embedding有限形状。17项 reviewer自加“恶意shape但给匹配canonical hash”的SQL负例全拒绝，见§5 |
| 单一profile与fingerprints | pass。snapshot整体hash、mode一致；lexical config hash与整个profile不同；hybrid tuple精确对应，SQL可表示string与Unicode escaping有实际PG对照；null/缺失值以IS TRUE/IS NOT TRUE等方式fail closed |
| 源metadata隔离 | pass at metadata scope。workspace composite FKs；current kind/version/hash/membership；owner NULL/audience workspace；真实private instruction metadata无法成为entry或激活shared corpus。未证明native issuer/reader权限 |
| chunk/range/hash/state | pass at local checked scope。1200 ceiling、1000起点步长、final推进、ordinal/count、实际codepoint length及text SHA；pending/retired不满足激活；zero member需service证明原文确空 |
| vector/profile | pass at SQL compatibility scope。vector(1024)、nonzero ready以及真实NaN/Inf/维数负例；lexical tuple NULL。synthetic正例不证明embedding来源、相关性或hybrid可用 |
| activated immutability | pass at tested current-state paths。snapshot/profile/source-set/generation等激活后及retired后不可改；active entry INSERT/UPDATE/DELETE拒绝；retire后允许清理 |
| 并发完整性 | **fail IS01**。默认READ COMMITTED的原9项真实并发已运行通过；其它可用隔离级别没有guard，旧快照反例失败 |
| native DDL与注册 | pass at explicit-import scope。独立process在import前后比较**原95个tables**及其全部index DDL，原项逐个不变，仅新增2表；根models无MemoryIndexManifest export。95是当前整合基线，不拿旧native85计数冒充当前基线 |
| migration/native/runtime/UI | not accepted，本grant外的required integration gates；不以ORM create_all替代 |

文件责任集中于这两个表的验证/DDL/触发器，未发现必须借本轮做无关拆分的理由。私有Python/SQL canonical helpers仅用于已验证有限domain，不是新增公共generic canonical API。

## 4. 自有 PostgreSQL 与原套件独立运行

完全独立新 cluster：

- data dir：`.local-runtime/index42-review-67c5ec1e2b0842ab9a460cf21555a206`（本工作树）；
- 仅监听 `127.0.0.1:58211`，新role `index42_review`；
- 新数据库 `citeframe_history42_index_test`（测试安全检查要求的名字，处于此独立实例）；
- PostgreSQL **17.11**、`pg_trgm 1.6`、`vector 0.8.6`，UTF8/C locale。

原测试 fixture 每轮创建唯一schema并finally DROP；独立探针也用同一真实fixture建立自己的schema。未连接开发者memory42、#46或任何现有runtime数据库。

命令（cwd本树）：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:CITEFRAME_HISTORY42_INDEX_POSTGRES_URL='postgresql+psycopg://index42_review@127.0.0.1:58211/citeframe_history42_index_test'
# PYTHONPATH只显式指定本树 backend-contracts/src、memory-service/src、backend-persistence/src。
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -m pytest packages/memory-service/tests/test_history_index_postgres.py -q -p no:cacheprovider
```

**138 passed in9.27s，exit0，零skip。** 包括9个真实dual-connection cases，未替换repository/authority。测试锁超时1s来自fixture，不代表该schema自动配置生产超时。

独立catalog核验实际4个用户triggers、两条复合FK及RESTRICT；原套件核验实际GIN/GiST/HNSW/active unique。FTS/trigram测试是C-locale的词法SQL证据，未扩成native search或hybrid质量。

初始化自己的新cluster成功；`pg_ctl start` 遇Windows restricted-token启动错误后，用同一已允许的postgres.exe、同一新data dir、hidden窗口直接启动（无提权）。未触碰denied uv或其它lane进程。最终停止与清理确认见本文件末尾。

## 5. Reviewer新增有限反例与测试oracle建议

### 5.1 Shape不能只靠错误hash被拒

当前 `test_source_set_shape_sql_admission`（:448）和 `test_profile_shape_sql_rejects`（:483）的一些 malformed payload仍携带默认合法对象hash。因此仅观察INSERT失败，不能区分shape拒绝与hash mismatch；未来若误删trigger shape检查，这些case仍可能因hash不匹配而绿色。这是回归oracle改进建议，**本轮没有据此宣称当前shape实现失效**。

本reviewer补了17项独立SQL controls：对每个malformed payload先用真实SQL canonical helper计算匹配hash，然后分别断言validator返回false、实际raw manifest INSERT抛SQLSTATE23514。覆盖非array、unknown/missing key、bool/fractional/out-of-range version、duplicate/非canonical source ID、unknown profile mode/space/version、非法embedding、bool size、数值threshold、hybrid空provider/model/modelVersion。全部拒绝：

`MATCHING_CANONICAL_HASH_MALFORMED_SHAPES_REJECTED 17`。

另检查SQL/JSON null与非object profile等有限值返回false。建议原owner将匹配hash的关键负例并入重工测试，保留当前canonical固定golden。

### 5.2 IS01复现调用方式

独立 `python -B -` 内存脚本用 `runpy.run_path('packages/memory-service/tests/test_history_index_postgres.py')` 加载本候选；调用 `pg.__wrapped__()` 取得真实独立schema，使用 `ready_manifest` 仅生成有效fixture。随后通过 `engine.connect().execution_options(isolation_level=...)` 与独立 `engine.begin()` 发出§2原始SQL，并由新连接观察已提交结果。没有修改原test/model，没有fake authority；fixture只代表真实落库的synthetic metadata。

DELETE与pending两个反例分别比较READ COMMITTED/REPEATABLE READ，共4次确定性事务交错。每次reader/writer实际使用不同数据库connection且A事务跨越B的提交，故覆盖的是原9例未覆盖的“持有旧snapshot、竞争方已释放锁”的窗口。

## 6. 保留的required downstream gates

- declared集合不证明maintenance builder枚举了全部workspace可读原文；empty original、原文slice equality、reader-before-BODY/索引评分权限仍需真实native owner。
- 激活后source/native变更（含同事务先激活后改source）、all-generation erase、source tombstone和direct/transitive summary/checkpoint/tool-result suppression仍依#43 single successor集成；本grant无新hooks，不能据行锁宣称自动retire现有index。
- 单一实际successor migration必须重现函数/表/触发器/索引并验证populated upgrade/rollback和集成锁序；当前ORM独立schema不覆盖。
- 其它source kinds、真实budgeted hybrid、search runtime/API/UI和CI执行门槛仍是必须完成的后续工作，没有静默删减完整目标。

本轮只新增本review和自有PG临时数据/log；没有产品/test/合同/Git改动，没有#46进程/browser、uv或模型/付费调用。verified durable结果保存在本review，未写private/global memory。等待原owner在同一有限文件集修复IS01后提交新的冻结候选。
## 7. 自有资源停止确认

最终只读查询确认自有DB中 `history42_index_%` schemas 为0。核对postmaster.opts的完整data dir/loopback端口及本轮owned PID后执行 `pg_ctl -D <上述唯一data dir> -m fast -w stop`，**exit0，server stopped**；随后 `postmaster.pid` 不存在、owned server进程已退出，log记录 database system is shut down。保留自有临时data/log供复核，未递归删除任何目录，未停止其它实例。