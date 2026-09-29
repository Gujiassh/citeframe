# History / GenerationImage pure CI — 独立定向审查

日期：2026-09-29。

**当前结论：bounded ACCEPT 当前精确 workflow、737a5a85 测试源及 checkout-local 依赖接入。当前42项测试已按完整源/冻结实现/原合同重新独审，依据见 §8。历史精确差分不可恢复，本结论不声称旧/新测试正文等值。**

没有发现本次有界代码/测试/runner 的阻断问题。§6 保留历史证据限制，验收已转为当前完整测试源的独立语义审查及实际运行。旧 evidence 的“已证明只删 loader/正文未变”表述不予采信，交付文案由 controller 更正。uv frozen installation 与 hosted execution 均未通过，本机 runner 结果不替代它们。

## 1. 范围与精确候选

目标：让已接受的42个 pure-history 和59个第一阶段 GenerationImage 用例在当前 checkout 的真实依赖上由独立 CI job 全量运行；禁止 sibling 注入、漏收集、跳过、xfail 或未执行被报告为成功。原 pure/history/type 的功能边界保持，未接受 source issuer/index/native image/runtime/DB/UI。

| 候选 | SHA-256 |
|---|---|
| .github/workflows/memory-history-contracts.yml | f62da08e231908e699158aee4c9e7a9dc34285d6576f2d9d8b7f4ffd97abc318 |
| packages/memory-service/tests/test_history_sources.py | 737a5a85b8aa46331790b4cfe83c9e0302c72894e8352bc5b73788f7f5f6daee |
| specs/v5/memory-management/evidence/issue42-history-ci.md | 3de1dd9150153dde290755009c54c40ba5e1c33df2f464b1a07b2f3cd9d68f92 |

## 2. Workflow 静态判定

**pass at bounded workflow scope。**

- 独立 ubuntu-latest job；pull_request 与 push main 触发，无 path filter、continue-on-error 或成功 bypass；contents:read、10分钟 timeout。
- 安装命令为 `uv sync --project apps/api --frozen --extra dev`；执行为 `uv run --project apps/api --frozen --no-sync python`。现有 API pyproject 以 editable path 指向本仓 contracts/memory-service 等包。未改 shared ci.yml、lock、产品或其它 gate。
- runner 前后核对7个实际 module.__file__，必须对应本 checkout 的确切路径；拒绝 CITEFRAME_HISTORY43_SOURCE_ROOT 和 PYTEST_ADDOPTS。环境禁用第三方 pytest plugin autoload。
- 两个固定 test 文件必须存在；每个文件精确42/59，101个唯一 nodeid。skip/skipif/xfail marker 直接拒绝。
- 每个 nodeid 必须且只能得到按顺序的 passed setup/call/teardown；非零 pytest 状态、skipped/wasxfail、少阶段/重复阶段/额外结果/完全未运行均失败。
- pytest.ini 默认不收集这两个文件的问题由本 job 显式传入这两条路径解决。固定计数是防漏执行门；真实语义测试及失败阶段检查仍是必要证据。

## 3. 依赖来自本 checkout；accepted blob 身份

依据 controller 指定的 accepted commit `b4e773a8fed882cd8cd8c6164c2b8814299eab56`，独立执行只读 `git rev-parse <commit>:<path>` 与 `git hash-object --path=<path> <path>`（无 -w）：

| 文件 | accepted/本树 Git blob（相同） | 本树 SHA-256 |
|---|---|---|
| packages/memory-service/src/citeframe_memory/compaction/policy.py | 385adc17032eef4cdd9e029835e54aeca4292342 | f992b4d5e0d512a6cae7756cab3ed0e33def8f178a4948c05a919dc9b2796b44 |
| packages/memory-service/src/citeframe_memory/compaction/__init__.py | 4204925da7c34f0248c138595bdf786efca3dd57 | 2026cc0cd44d5f3475f58b0abee0a8f6531328d3e24ffb992150202cec5bdd0a |
| packages/backend-contracts/src/citeframe_contracts/compaction.py | 8ee09d298de9b39e76457d0beb7758b3a0a57207 | d77617a25ecf5cd9c0b808537f6c884b7ee67e2a2250bb0d955e99597ddb5e2b |

**精确说明：**本树这三份工作文件为 CRLF，Git blob 为 LF；直接 raw byte comparison 不相同，去除该换行差异后全部相同，Git clean-filter blob identity 也相同。不能将“Git blob 相同”写成 checkout CRLF 原始字节与 LF blob 逐字节相同。内容/实际函数没有改动，canonical DTO 的既有本树 D776 SHA 保持。

## 4. 本 reviewer 独立运行原 runner

从 workflow 中 `from collections import Counter` 到 heredoc terminator 前，**只去掉 YAML 的10空格缩进**，保留完整正文执行。提取后正文 SHA-256：

`aeeff0148ccb739e95fb2000b249eec1e30c2561b36e359985a268c79191de13`。

执行环境：`D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -c <原正文>`；cwd为本工作树；PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1；PYTHONPATH只显式指定本树 packages/backend-contracts/src、packages/memory-service/src、packages/backend-persistence/src。没有设置 sibling 环境变量或修改 runner 来添加依赖。

**实际结果：101 passed in 6.71s，exit 0。** 运行前后均输出7个 checkout-import，并最终输出：

`pure-contracts-executed=101; history=42; generation-image=59; skipped=0; xfailed=0`。

实际路径为本树 contracts memory/compaction/history、memory compaction init/policy、history ranges/search。没有使用 sibling policy，也没有 stub。现有 venv 仅提供本地 interpreter/已装第三方库；此结果不是本 job 的 frozen install 结果。

## 5. 独立 fail-closed 负例

### 5.1 实际 pytest 故障注入

在独立子进程中保留同一 runner 正文，只在调用 pytest.main 时附加 reviewer 内存 plugin；未改 workflow 或测试文件。

| 实际注入 | 实际结果 |
|---|---|
| 在第一个 history case 的 setup 中 pytest.skip，未附加 skip marker | `100 passed, 1 skipped in 6.94s`，**runner exit 1**；没有成功101标记 |
| collection_modifyitems 删除第一个 history item | **exit 4**，contract_collection_mismatch，实际41 history +59 image；没有成功101标记 |

额外独立子进程：设置 sibling环境变量、设置 PYTEST_ADDOPTS=--collect-only，分别在测试前拒绝 sibling_dependency_forbidden / pytest_options_override_forbidden。另将缓存中的实际 policy module.__file__ 改为非checkout sentinel 路径，测试前拒绝 non_checkout_import。全部仅为进程内故障注入，无文件写入。

### 5.2 同一 ExactRun class 的有限 hook 控制

从正文 AST 提取原 ExactRun（没有改判定逻辑），用合成 pytest item/report 调用其 hooks：

- skip、wasxfail、not_run、missing_teardown、duplicate_call、missing_collection 六项全部 TESTS_FAILED。
- 额外 report、原 pytest 非零退出也全部失败。
- collection 少case、重复nodeid、skip/skipif/xfail marker 五项全部抛 UsageError。
- 精确101项且每项三个 passed phase 的正例保持成功。

这些合成 hook 控制与上面的实际101运行、真实skip/deselection负例分别记录；不能把 synthetic reports 当 hosted run。

## 6. HC01 — 历史精确差分不可恢复；改用当前源的独立证据

旧文件 SHA-256 为 `22ec11d67fe74a221b38dbed6a0a3d39fda538d5e1f7f09c66dd661f7883b944`。旧原件无可验证保留副本，也无对应 Git 历史；有限恢复没有匹配。**历史精确差分不可恢复；撤回“已经证明只删 loader/正文未变”的确定性说法。** 未匹配不构成正文发生改变的证据，也不继续据此要求重建旧文件。

当前验收对象改为 hash `737a5a85…` 的完整现存测试源。§8 基于已批准2bef合同、冻结 history 实现、原 review 的语义 oracle、同hash实际101运行和新增定向控制重新独立判定。交付阻断以该新证据关闭，历史等值仍不成立。本结论不接受旧 evidence 中相反的确定性文案；controller应在交付 evidence/ledger 中保留这一限制及新的验收依据。

## 7. uv、hosted与冻结范围

- 开发者报告 `uv sync --frozen` 启动被 OS 拒绝。本 reviewer独立执行 `uv --version`，同样在启动现有 uv.exe 时收到“拒绝访问”，exit 1；没有寻找替代 executable 或绕过限制。**未执行成功 frozen sync/install**。
- **未执行 hosted workflow**。controller 后续在另分支提交/推送并观察实际 install+job；本机runner通过不可写为 hosted CI绿色。
- 类型三份冻结文件仍为 memory.py `f168652d…`、contracts/__init__.py `90096c37…`、test_generation_image_contract.py `49e806b7…`；全hash与原接受值相同。history产品/DTO未修改；原 GenerationImage review仍为 `b1162d262e826317a5cffe53e97236e157c842db8f9f57424973ca11df34f1a9`，原 history review仍为 `f14a8a77992665580f9bdd4b07045ac4601892d03cc39251d92865d962f952ec`。
- 无 ABI/权限/source/schema/PG/UI/视觉 runtime 扩张，未重审或接受 #43 核心；没有 provider/model/paid调用。

本輪只新增 `reviews/issue42-history-ci.md`，未改任何产品/tests/workflow/evidence、原review、Git、private/global memory或canonical #40。durable write-back仅此新评审。


## 8. 当前737a5a85完整测试源语义复审 — 2026-09-29

**bounded ACCEPT。当前42项用例与补充独立控制足以支持既有 pure-history 范围和本 CI 接入，不新增产品/权限能力接受。**

### 8.1 实物及审查方法

重新完整阅读当前 `packages/memory-service/tests/test_history_sources.py`，核对实际 imports、全部19个 test函数、fixtures/helpers、parametrize 参数和真实断言；通过读取其 pytest mark 展开，明确得到42项。没有从“总数42”推导语义充分性。

对照的冻结实现为：

- contracts/history.py：`a771d0caf41ac0da307e1bb723da039aa2411f9cc35dd86e4c2ee460cf9d3c02`；
- history/ranges.py：`65f068f1003692f0b30e4f7f0daa8c4ab3993b2f5fd44c6686163dca93669d08`；
- history/search.py：`1e399094f51ae3f4dcfd9c25474584ab85193ce745410fc836704a2433fa334f`；
- 原合同：`2befea01c88ff5fc7d3f8f54c23c9f22b9bb850dd5619dbf819d1091dcf3c042`，范围/当前请求计数/固定窗口及形状边界；原 history review 的 pure限定继续有效。

当前测试直接 import 本 checkout 的 canonical SourceReference 和实际 compaction.policy，没有 sibling loader。CharacterCounter 是显式 estimated、完整 asdict(request) 的 JSON code-point fixture；它保留实际收到的 requests，未替换 count_request、窗口或解析器。该 fixture 不证明实际 tokenizer精度、provider价格/能力或授权。

### 8.2 全部42项的逆向 oracle 判定

| 组与参数数量 | 当前真实断言及反向失败信号 | 判定 |
|---|---|---|
| Canonical SourceReference：1 | exact class identity，禁止测试自行复制三元组类型 | pass |
| Policy shapes：11（legacy1、enabled1、拒绝9） | v1不改输入且disabled；v1加history/v2缺history拒绝；enabled scopes/kinds有序tuple；错误bool/audience/未知键、空/非法scope、重复/私有kind、未知版本拒绝。测试成功只证明shape projection，未宣称验证parent budget/deadline或native授予 | pass at shape scope |
| Query/projection：8（拒绝7、投影1） | current_branch不能用threadId扩展或显式note；thread缺ID、bool limit、未知字段、无时区、空kinds拒绝。corpus集合保持不变，按传入authorized/scope相交，disabled kind拒绝。没有把 supplied authorized set 当实际ACL证明 | pass at pure scope |
| 原文/窗口/range：13（精确窗口3、非法窗口4、空/变更1、整数5） | >4000字符、BOM/CRLF/astral/组合字符；全体页面拼接等于选择窗口，start推进、terminal end固定；span=null扩展/超长span/未解析locator/bool拒绝；空原文terminal、原内容变更/hash不符拒绝；负数/相等/反向range拒绝 | pass，独立golden坐标补证见下 |
| Cursor/retry：2 | MAC修改、binding变更、expiry拒绝；相同cursor重复计算相同结果和selection | pass，仅纯确定性重算；不声称durable archive lost-ack |
| 当前请求计数与容量：7 | C1→C2新ID/framing/profile从原end继续并缩页；siblings/tools/prefix保留，独立request hash；no-fit原cursor可重试；当前profile/counter不符拒绝；缺sibling/物理容量不符拒绝；1500-prefix非单调额外成本强制重新计数到750；profile变化有新hash、credential变化不入profile；16000 codepoint ceiling及耗尽窗口拒绝 | pass at supplied-request scope |

若实现回到第一页、重复扩窗、按UTF-16切片、丢失sibling、跳过当前counter identity/full capacity、接受未终止空页或令合法projection改变corpus，当前断言及下述控制会失败。原 tests 中部分期望终点来自 window自身，request-hash检查也使用产品helper；本轮额外使用独立固定坐标与标准库公式，避免只验证产品内部自洽。

完整权限/source reader-before-BODY、源删除/ABA、SQL、registry、lexical/hybrid、native发行/政策冻结、archive/CAS/dispatch仍在pure范围之外；42项参数中的权限形状拒绝不能关闭这些门槛。

### 8.3 新增独立定向控制：真实累积tool批次和当前请求

使用内存 `python -B -` 脚本、当前文件的显式request/render/CharacterCounter fixture及本 checkout 实际产品函数；无测试/产品文件写入。新的证据不依赖历史22ec的恢复。

- 原文为包含BOM、中文、emoji、组合字符、CRLF、引号、反斜线、NUL的10-codepoint片段重复500次。selection=[53,4200)，before=50、after=77，**独立期望窗口固定为[3,4277)**；未从产品属性生成期望值。
- C0之后，每次将上一轮的**完整已填充 GenerationRequest.messages** 保留，再追加下一轮真实形状的assistant两项tool-call和有序两项tool-result batch；调用ID均不同。不只添加一条代表“增长历史”的user文本。
- 每页改变fixture model/profile、合法physical容量及output reserve；严格核对所有前序完整results与sibling内容均保留。逐页用标准库JSON/SHA重新求request hash，单独核对fixture完整请求token数、当前hard ceiling和content delta。
- **实际20页、最终62条messages**，严格从前页end推进；最终拼接精确等于原文[3,4277)，expiry保持900。
- 完整历史累积在33,000输入ceiling下实际触发capacity拒绝；原cursor/window未变。随后显式传入120,000的测试ceiling，在同一cursor继续；另有一次ceiling=100的故意no-fit控制。测试connection物理上限覆盖这些显式测试预算，不授予生产自动扩额、compaction或模型能力。

首次完整累积尝试确实遇到33,000容量上限，未将其记作通过；后续脚本明确断言该拒绝和同cursor重预算恢复。最终输出：

`ACCUMULATED_COMPLETE_REQUEST_PAGES 20 EXACT_WINDOW 3 4277 FINAL_MESSAGES 62 SAME_CURSOR_REBUDGET 1`。

另补 **24项明确拒绝**：no-fit；TokenCount 的bool/负数/float及counter id/version/mode/config漂移；tool-result错序/缺失/错ID；private audience/memory_instruction、重复/非法scope、非bool enabled；query注入 actorUserId/audience/workspaceId/destinationId；query空/4001、cursor=None、时间反向。全部匹配稳定错误code。另验证4000-char/limit20正例、current_branch排除note，以及空authorized set得到空交集而corpus保持不变。

实际输出：`ADDITIONAL_CURRENT_SOURCE_REJECTIONS 24 PASS`。这些是独立临时控制，不宣称已经成为CI内的额外用例；无fakeauthority/native/DB/provider执行。

### 8.4 本次接受与交付约束

- 复用 §4 中**同737a5a85测试hash、同f62da08e workflowhash**的真实101通过及 §5 的runtime skip/deselection/环境/import负例；不重复1664 type/admission或完整设计审查。
- bounded ACCEPT覆盖当前 workflow、当前42项测试源和本 checkout依赖，足以让controller按原计划独立分组交付。原历史精确diff无法证明的限制保留；不能在文案中恢复“已证明正文等值”。
- §1 的旧 developer evidence hash用于观察/归因。其旧历史等值断言不作为本次接受证据；controller收窄文案和交付ledger后记录新文档hash，不需要据纯措辞修正重开产品审查。
- frozen install、hosted job仍待实际成功；本机runner不能代替。类型三份已接受hash、history产品hash、原authority/reviews均保持；未扩成source/DB/UI/model视觉可用。

本轮仅更新本CI review。未继续寻找/制造旧文件，未修改产品/tests/workflow/CI/evidence或旧两份review，未进行Git写入、模型/paid调用。durable write-back仅本评审。

## 9. HC02 — PR56 全 API import-boundary guard 的有限白名单过时（2026-09-29）

**结论：需要原 owner 定向修正测试；当前失败没有发现 forbidden 跨包依赖。原 pure-history/type/专用 CI 的 bounded ACCEPT 保留；全 API gate 尚未关闭。**

### 9.1 目标、候选与精确失败点

本轮只判断第三项 contracts import-boundary 失败的根因和最小修复面；另外两项 #43 a2a differential 失败由 #43 负责，未审查。当前 index 两文件施工不属于本轮。

PR56 候选：`a3c9a3ccd68190377fc9e236b14e352e98d424ea`。独立比对 `git show a3c9a3cc:<path>` 与工作文件（只消除 Git/checkout 换行差异），下面两份内容相同，无本地 diff：

| 文件 | 本树 SHA-256 |
|---|---|
| apps/api/tests/test_deploy_dependencies.py | 95d147b8434f94adb59b099891b2bcbfc3b0e466ac1286548659dc6e59952729 |
| packages/backend-contracts/src/citeframe_contracts/history.py | a771d0caf41ac0da307e1bb723da039aa2411f9cc35dd86e4c2ee460cf9d3c02 |

精确函数：`apps/api/tests/test_deploy_dependencies.py:74`，`test_contracts_source_is_pure_and_imports_with_only_its_source_path()`。

失败断言在 **:83–85**：每一个相对 `ast.ImportFrom` 都必须等于唯一三元组 `("citeframe_contracts/__init__.py", 1, "memory")`。实际扫描到 **contracts/history.py:7** 的 `from .compaction import SourceReference`，三元组为 `("citeframe_contracts/history.py", 1, "compaction")`，因此失败。即使仅放行这一行，**:8** 的 `from .memory import MemoryError` 仍会被同一旧断言拒绝。

这里的 `.compaction` 解析为 **citeframe_contracts.compaction** canonical DTO；`.memory` 解析为 **citeframe_contracts.memory**。它们均为同包纯合同依赖，不是 `citeframe_memory.compaction` 服务实现，也没有导入 application/persistence。保持这两条引用可保留 canonical 类型/错误身份，无需复制定义或修改冻结产品。

### 9.2 独立复现与边界证据

原失败测试实跑（cwd 为本工作树）：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -m pytest apps/api/tests/test_deploy_dependencies.py::test_contracts_source_is_pure_and_imports_with_only_its_source_path -q -p no:cacheprovider
```

结果：**1 failed，exit 1，0.16s**；错误指向 test **:83**、history **:7**，与 controller 提供的 hosted 症状相符。测试在 AST 断言阶段终止，尚未到原函数的 subprocess smoke。

额外只读探针：

- AST 扫描当前 contracts 的全部5个 `.py` 文件；相对导入实际仅有3种三元组：root `__init__.py → .memory`（:423、:460 两处），`history.py → .compaction`（:7），`history.py → .memory`（:8）。
- 所有绝对 import roots 为 `__future__, base64, binascii, collections, contextlib, dataclasses, datetime, typing, uuid, zlib`；全部属于 stdlib。manifest 的 `project.dependencies == []` 保持。
- 用现有 Python 启动 **`-I -S -B -c <probe> <contracts-src>`**；禁用 site 初始化、忽略 PYTHONPATH，只显式插入本树 contracts source，实际导入 root/history/compaction/memory。四个 `__file__` 均精确匹配本 checkout；`history.SourceReference is compaction.SourceReference` 与 `history.MemoryError is memory.MemoryError` 均成立；未加载 citeframe_memory/citeframe_persistence/app/sqlalchemy/pydantic/fastapi。exit 0。
- 在内存中验证下面建议的有限谓词：3种批准三元组通过，9项 forbidden absolute root / 相对 depth / module / origin 控制拒绝。包括 sqlalchemy、fastapi、citeframe_memory、citeframe_persistence、`..memory`、`.unknown`、`from . import memory`、未批准 origin 的 `.memory`，以及原 guard 不允许的 absolute self-package import。此为建议谓词的 reviewer 控制，**未修改或声称修复后的真实测试已经通过**。

### 9.3 最小修复建议及复验条件

由原测试 owner 在 controller 授予的窄范围内修改 `apps/api/tests/test_deploy_dependencies.py`：将单一相对导入等式改成以下**显式有限集合**的 membership 检查：

```python
{
    ("citeframe_contracts/__init__.py", 1, "memory"),
    ("citeframe_contracts/history.py", 1, "compaction"),
    ("citeframe_contracts/history.py", 1, "memory"),
}
```

保留 `dependencies == []`、现有 stdlib-only absolute root 检查和 `(path, lineno)` 失败定位；不要采用“所有相对导入直接 continue”、self-package 通配或允许 `..` 越界。原 local-package/export/lock/Docker finite maps 不需改变。

原 source-path smoke 只 import root package，没有显式加载 history；建议在同一个隔离 smoke 中显式 import history/compaction/memory，核对精确 source 路径及 canonical 类型身份。保留旧 forbidden-import 保证，并为新增 allowlist 附加 finite negative controls（错误 origin、module、depth、第三方/application/persistence/service roots）；不可删除 guard、改变 baseline 以忽略整个 history 文件。

修复后的验收需实际原测试/相关 deploy 测试通过且负例继续拒绝。该定向修正无需改 history 产品、DTO、lock、workflow 或中断 index 施工。本轮只提交 finding/建议，没有实施修复，HC02 尚待 owner 候选与复验关闭。

### 9.4 hosted 更新与范围保持

controller 报告 PR56 `a3c9a3cc` 专用 frozen101 hosted 已通过；全 API 在 run **36464968435** / job **109072636943** 有上述第三项及两项 #43 a2a 失败。本轮未重新下载 hosted log，因此 hosted 状态明确归因于 controller；本 reviewer 独立证据是同候选内容的本地精确失败复现和隔离 import/AST 检查。§7/§8 的 hosted 未运行描述保留为当时的证据状态，以本段补充后续进展；本机 uv 启动受限的既有事实未改变。

未将专用101通过扩大为 full API/PR/source/DB/UI/model image runtime 接受；既有 P1a、admission、pure-history、第一阶段 image 接受范围保持。仅追加本 review，未改产品、测试、workflow、其它 review、Git 或正在施工的 index 文件；没有 paid/model 调用。write-back 检查：可复用的已验证根因与证据保存在本项目评审，不重复写 private/global memory。
## 10. HC02 exact fix — CLOSED / bounded ACCEPT（2026-09-29）

接受精确 `apps/api/tests/test_deploy_dependencies.py` SHA-256 **1d17c3ada08dc31f58c1c875ce830f9099c92d47132de9eb7d29a1bf9b19532f**。HC02 所指第三项 import-boundary 失败在该本地候选上关闭；不据此声称 controller 尚未推送的 hosted 全 API 已通过。

### 10.1 实物与旧边界保持

- 原 AST scanner 抽为 `_assert_contract_imports`，仍遍历整个 contracts source tree。相对导入只批准 `(origin, level, module)` 的3个精确三元组：root→.memory、history→.compaction、history→.memory。不是全包/所有relative放行。
- 空 dependencies、stdlib-only absolute roots、AST 全树扫描与带 path/lineno 的错误保持。旧 local distributions/source/lock/export/Docker 期望没有改动。独立以 `git show a3c9a3cc:<test-path>` 作 AST 比较，除目标函数外原有8个 functions/helpers 完全同 AST；原 top-level assignments 全部保持。
- 3项 positive 参数用例另断言 allowlist 精确等于该集合；16项 negative 均调用同一实际 helper 并要求 AssertionError 与 origin/line 定位。覆盖错误 origin、二/三级相对深度、未知module、空relative module、absolute self-package、third-party/API/Worker/persistence/research-persistence/memory-service，以及同一 import 中混合 stdlib+forbidden root。没有删除旧 guard 或放宽既有 package baseline。
- 隔离 smoke 实际使用 `-I -S -B`，只插入本 checkout contracts source；显式导入 root/history/compaction/memory，四份 `__file__` 精确等于期待路径；SourceReference、MemoryError canonical identity 有真实断言，并拒绝已加载 forbidden module roots。smoke 随原测试实际执行成功。

### 10.2 本 reviewer 独立运行

Interpreter 为 `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe`；cwd为本工作树，`PYTHONDONTWRITEBYTECODE=1`，`-B`、`-p no:cacheprovider`。

1. API：`python -B -m pytest apps/api/tests/test_deploy_dependencies.py -q -p no:cacheprovider --basetemp=<本树.local-runtime下新唯一hc02-review目录>` → **25 passed，0.28s，exit0**。包含原6项、3项精确positive、16项negative。保留一条现有 Starlette/httpx deprecation warning。
2. Worker：独立进程 `python -B -m pytest apps/worker/tests/test_deploy_dependencies.py -q -p no:cacheprovider` → **2 passed，0.05s，exit0**。未混合两个同名测试模块。
3. 同一 workflow 原 heredoc正文再次独立执行（仅去 YAML 10空格缩进），body SHA-256仍为 `aeeff0148ccb739e95fb2000b249eec1e30c2561b36e359985a268c79191de13`；禁用第三方 plugin autoload，PYTHONPATH仅本树 contracts/memory-service/backend-persistence。→ **101 passed，6.09s，exit0**；七个 checkout imports 前后验证成功，最终 exact42+59、skipped0/xfailed0。

首次 API 命令未指定 basetemp 时出现 **24 passed / 1 setup error**：既有 Docker parser 用例的 tmp_path 无法扫描系统 `pytest-of-baiao` 临时目录（WinError5），未执行该用例正文。保留此失败记录；随后只将测试临时输出定向到获准可写的本树新唯一目录，未删除共享临时目录、修改测试或绕过产品 guard，得到上述25项全过。

### 10.3 接受边界

接受本次 test-only 修复及其有限 boundary controls；保持先前 pure-history/type/CI 接受。开发提供的25+2+101结果已由本 reviewer 独立复验，仍是本地现有 interpreter 结果；未重新执行 uv frozen install 或 hosted job。另两项 #43 a2a 失败不在本轮，也未改 baseline；本轮不混入 index 设计/实现、PG或新 native authority 认可。

本阶段只追加此 review；测试临时 fixture 输出在本树独立目录。没有产品/test/workflow/Git写入、付费调用。精确候选通过后再串行进行独立 IC01 文档复审。