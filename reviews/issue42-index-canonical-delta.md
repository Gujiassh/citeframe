# Issue42 index canonical delta — independent bounded design review

日期：2026-09-29。

**当前结论：IC01 CLOSED；bounded design APPROVE 精确合同 3e8a8f2f…，见 §7。实现/PG/激活尚未接受。**

**首轮结论（已由 §7 关闭）：NEEDS ONE BOUNDED CLARIFICATION（IC01）。profile_snapshot 与两个 fingerprint 的分工、source-only workspace 范围及单一 profile 关系可以接受；当前精确候选尚不能整体标为设计 APPROVE，原因仅为 Python/JSONB 的 strict integer/canonical 边界未定清。** 不重开既有 §7 设计；不要求停掉无关实现。没有接受现有 partial 模型或39项 PG 未覆盖的约束。

## 1. 目标、候选与证据范围

审查对象：`specs/v5/memory-management/lanes/issue42-index-canonical-delta.md`。

SHA-256：`952d5dcebca3836a85575785bf7c6909998157bf6931a30f92d3236d2dd5cf0c`。

只判断 source_set 的精确编码、entry.config_fingerprint 与 manifest.profile_fingerprint 的关系，以及新增 profile_snapshot 与已接受 shared-sources §7 / §8 的兼容性。对照 `issue42-shared-sources.md` 的源权限/完整 workspace corpus/原子失效约束、两文件 grant，并只读当前 partial model 与标为 PARTIAL 的 evidence。未把正在施工的模型当冻结实现审查，也没有检查或修改 HC02 候选。

验收 oracle：同一受支持值在 Python/PG 得到相同 canonical bytes/hash；每个 manifest 只有一个明确不可变的 retrieval profile，entry 严格匹配其子配置；原文/source 权限仍由真实 native owner 控制；完整性/激活不能以先读后写竞态绕过。设计认可与实现/PG/迁移/激活认可分别记录。

## 2. IC01 — 明确 raw JSON / Python value / JSONB 三层的整数域与 canonical 规则

**优先级：P2，阻断精确 canonical 子合同的整体批准。位置：Source set 段，以及 profile_snapshot 中所有固定整数。**

候选同时规定 strict positive/nonnegative integer、拒绝 fractional JSON numbers/implicit coercion，并用 Python 风格的 sorted keys / compact separators / ensure_ascii=False 定义 canonical；落库类型为 JSONB。当前文字没有区分“拒绝有小数值”与“拒绝所有浮点/指数形式 token”。这两者在 Python 与已转换的 JSONB 上不能视为同一个可检验条件。

具体边界：Python `json.loads('1')` 得到 int，`json.loads('1.0')` 和 `json.loads('1e0')` 都得到 float。PostgreSQL JSONB 存储 numeric，不保存 Python int/float 类型；指数输入转换后也不能可靠恢复原 token spelling。即使最终 hash 用无小数的 `1`，也不能由一个 JSONB guard 宣称已经拒绝所有原始 exponent/float token。`chunk_count=-0` 和零的原始拼写也不能从存储值恢复。

因此原开发需要选择/落实明确的两层规则，不能自行假设数据库已替应用验证 lexical type，也不能把 jsonb 的 spaced `::text` 直接当 canonical。建议最小澄清：

1. 应用 admission 的整数严格为 Python `type(value) is int`，bool/float 不接受；原始 JSON 如经此入口解析，`1.0`/`1e0` 相应拒绝。数组仍不得重排、去重或隐式转换。
2. 明确 JSONB SQL guard 的可实现域：检查 numeric 类型、数学整数性、范围，或明确选择可观察的 decimal-scale 规则；**直接 SQL 经 JSONB 已丢失的原 token 形状不作“已经拒绝”保证**。如果要求连 direct SQL 的原 token 都严格拒绝，则必须在转换为 JSONB 之前验证，不能声称单靠当前新字段做到。
3. 对所有被接受的存储整数，canonical 输出规定为不带指数/小数点的十进制整数，零为 `0`。先验证再序列化/hash；固定 profile 常数也遵守同一规则。
4. 固定 source version / chunk_count 的有限数值域，与 source_version BIGINT、chunk_ordinal INTEGER 的可表示/完整性范围一致；当前“正数/非负数”允许远超对应列的数值。具体上限由 controller 定稿，不应让 Python 任意精度与 PG numeric 的差异成为隐含合同。

这项澄清不要求新 native 表、私有 audience、generic canonicalization 框架或额外 source authority。可继续不依赖该裁决的模型/测试工作；受影响的 admission/hash SQL 应按补齐后的精确规则实施。

必要边界用例：`1`、`1.0`、`1e0`、true、负数、零、version/chunk_count 上限及上限+1；应用入口与 direct-JSONB 层分别列实际接受/拒绝，不伪称两层保留相同的 token 信息。重复/乱序 source IDs、unknown/missing keys、4096/4097项、canonical byte cap 则继续按本候选拒绝。

## 3. 已明确可接受的关系与既有设计兼容性

**pass at bounded design scope：**

- source_set 为严格 source_id ASCII/byte 升序数组；不按 locale 排序、不在 admission 静默重排；exact refs + chunk_count 足以表达零长原文。空原文与空 workspace corpus 的真实性仍须 native service 校验，metadata 自身不授予证明。
- manifest.profile_snapshot 是本次新且未激活的 manifest 表内的单一配置事实；required 字段、版本、mode/space/chunking/lexical/embedding 的有限形状可审，不引入第二份 source registry 或 native audience。
- manifest.profile_fingerprint 是整个 retrieval profile 的 hash；entry.config_fingerprint 是其 lexical 子配置或 hybrid embedding 配置身份。两者不应按相等关系约束；应由 profile_snapshot 内容与 tuple equality 约束对应关系。
- lexical tuple 全 NULL 与固定 lexical config hash兼容既有 §7；hybrid tuple 精确匹配 manifest.embedding，ready 才要求有效、有限、非零1024维向量。没有 model relevance 或 paid build 授权。
- fixed lexical/chunking 参数与 §7 一致；未知版本/字段 fail closed，mode 没有隐式 fallback。profile 中 provider/model/modelVersion 的字符串需以无 normalization 的 JSON string escaping 参与 canonical；实现跨语言 golden 必须包括引号、反斜线、控制字符、非ASCII/astral和组合字符，并明确拒绝 PG text/UTF-8 不可表示的输入（如 NUL/孤立 surrogate），不能用字符串拼接漏 escape。
- authority 仍在 §7/§8 的 workspace/native/source 元数据与真实读取许可；profile_snapshot 既不构成 authority，也不授权读 private revisions。原始 slice equality 仍是 native authorized adoption gate。

新增 profile_snapshot 必须一起进入 activated 后的 immutability guard（包括已 retired 的曾激活对象）；不能只验证一次 hash 后允许 snapshot 被改写。所有 hash/shape CHECK 或 trigger 要显式拒绝缺失/null，避免 SQL UNKNOWN 绕过；这属于本候选约束的实现验收，不是已完成的能力。

## 4. 激活竞态：沿用既有锁序，必须在实现证明

**设计兼容；运行证据尚无接受。** 候选的“serialize or fail safely / never activate partial or stale corpus”须与既有 §7/§8 合并解释，不能降为读取 source/profile 后做一次无锁 active UPDATE。

最小实现复验应包括：

- entry admission、building manifest 的 source_set/profile 修改、activation 和 chunk INSERT/UPDATE/DELETE 的交错；必须对同一 manifest 串行校验最终集合与 profile/generation。不能仅靠 active partial UNIQUE 推导 corpus 完整性。
- 激活检查覆盖最终每个成员的 kind/version/hash、expected count、ordinal/range/completeness及可用 state；不是仅重查提交中的一个 entry。激活后 table-local DML 不得让仍为 active 的 corpus 留下 missing/extra/nonready chunks；应拒绝或在同一事务安全退出 active。
- corpus replacement 在相同 workspace/source-kind 范围内串行，旧/新 active 切换原子；native/source 变更沿原 §8 的 workspace → native → source → consumers → index 顺序，校验与激活间不能放掉保护。
- native mutation hooks、整体 source retirement/删除/递归 invalidation 仍由既有 #43 single successor integration 负责。两文件 table-local PG 测试只能证明所实施的局部 barrier，不能自行模拟一个 permissive authority 并宣称 native 并发已关闭。

本段是原约束在当前 delta 上的直接验收边界，不批准新增 hooks/registry/migration/route，也不阻止当前隔离两文件继续推进。

## 5. 本轮独立有限计算（无 PG / provider 执行）

使用现有 Python，以 `json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')` 计算候选有限正例；没有修改产品/测试。结果可用于后续 PG golden 对照，当前并非 PG 对等证据：

| 样本 | bytes | SHA-256 |
|---|---:|---|
| empty source_set `[]` | 2 | 4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945 |
| 单成员 source_id=`00000000-0000-0000-0000-000000000001`, version=1, sha256=64个0, chunk_count=0 | 158 | 9c12d08632627dd760071d3c3bebee12c4b3b0046c860a03103d1b813ee19fdb |
| 候选完整 lexical profile | 282 | 2f42a80b403af92d175741eaa978ed0ebce028f362c5a0c5fe17fef53dde2538 |
| 候选 lexical entry config | 226 | e2f53590c07283726955744f0da86cdda46344cd59e36b0012b437aedfd34947 |

两个 lexical fingerprint 实际不同，符合分层含义。独立 Python token 探针也确认 int/float 区别：1→int/`1`；1.0和1e0→float/`1.0`；-0→int/`0`；0.0→float/`0.0`。本轮没有启动、连接或停止任何 PG 集群，没有把 PostgreSQL numeric/token 信息损失的设计判断写成已执行的 PG 测试。

## 6. 交付边界

仅新增本 review。未改产品、测试、contract、Git、其它 review 或 HC02 候选；未调用模型/付费 provider。39 PG 仍按开发者 evidence 标注 PARTIAL；尚未接受 profile_snapshot 实现、SQL canonical parity、全部非法 SQL、激活竞态、successor populated migration、native/source授权、完整共享搜索或 API/UI。

IC01 定稿后可以只重审该窄澄清并给 bounded design APPROVE，不需要重复整份 source/index 设计。实际实现接受仍需精确冻结候选与相应 real-PG 证据。durable write-back 仅本项目 review，不重复写 private/global memory。
## 7. IC01 narrow re-review — CLOSED / bounded design APPROVE（2026-09-29）

本轮在 HC02 修复完成独立复验并更新其原 review 后串行开展；只审 IC01 补充，没有重开 profile_snapshot/两个 fingerprint 的已接受关系或审查 index 实现。

**批准精确修订合同** `specs/v5/memory-management/lanes/issue42-index-canonical-delta.md`：

SHA-256 **3e8a8f2f98917545df3bafe19b83869db6dec32ee0b27a8c9f32f49b71974625**。

原 IC01 四项问题均已明确关闭：

| 边界 | 当前合同实物 | 判定 |
|---|---|---|
| 应用类型 | version/chunk_count 为 `type(value) is int`，明确拒绝 bool/float，包括解析为 float 的1.0/1e0 | pass |
| direct JSONB | numeric 必须数学上为整数；明示不保留所有原始数字拼写，不能证明 token 是否用过 exponent/decimal | pass，未夸大SQL可观察信息 |
| canonical | 先校验再转 base10 整数数字，无指数/小数点，零为0；不采用 spaced jsonb text hash | pass |
| 有限范围与固定数字 | version为1..9223372036854775807；chunk_count为0..2147483647；固定profile数字沿用应用strict type / JSONB mathematical equality | pass |

这些规则使 canonical 域可按有限 Python/SQL 实现：应用输入严格类型，数据库对已存 numeric 作数学值检查，二者共同产生相同被接受整数的十进制编码。direct SQL 与应用入口有意保留不同的可观察输入边界，不宣称原始 token 等值。INTEGER上限是本合同明确采用的 chunk_count 上限；无须反推更大的理论 ordinal 容量。原 lower/upper bound、unknown/missing keys、ordered unique source IDs 和大小限制继续生效。

未发现本次窄补充新增的具体阻断项。§3 的单一 profile/fingerprint/源权限判定与 §4 的激活并发验收要求保持；当前可依该精确合同在既有两文件 grant 内实施受影响的 profile_snapshot/source_set/hash/coherence 约束，不扩大为 native表、audience、registry、migration或route授权。

**这次是 bounded design APPROVE，不是实现通过。** 未运行或检查新增 PG 实现；原39PG仍为PARTIAL。Python/PG golden对等、directSQL非法值、NULL/UNKNOWN failclosed、完整集合/active DML并发、source/native集成、successor populated migration及API/UI仍按原分阶段门槛取得实际证据。§5 的有限整数正例及两个lexical fingerprint语义保持，不因设计批准变成PG运行证据。

本阶段仅更新此 review。无产品、测试、合同、Git或PG操作；未修改另一个lane的文件。durable write-back保存在两份各自范围的原review，不重复写private/global memory。