# Issue45 settlement CI — 独立 workflow 审查

日期：2026-09-29（Asia/Shanghai）

**判定：REWORK REQUIRED，仅 F45-CI-1（P1）与 F45-CI-2（P2）两项定点修正。** 本文独立于产品审查。产品 `reviews/issue45-settlement.md` SHA-256 `C7E70C027739D999C128B5609C64EB922B1E60BC50FFE9C08A3BCDC72B1BA9DB` 的 bounded APPROVE 保持不变；controller另行PG 56 pass/23.59s按controller提供的结果记录，不算本 reviewer 执行。

冻结lane：`D:/Code/citeframe-lanes/issue45-research`。

| 本次已审对象 | SHA-256 |
|---|---|
| `.github/workflows/research-memory-settlement.yml` | `F77E6FF9ED5C41D4995092FEFC8B442BCB96D01C829178E6B72A96BC0FBCB6DB` |
| `specs/v5/memory-management/evidence/issue45-settlement-ci.md` | `2FD7FDB89A7E72E7A3F3FFD0BFE149E3BDF7EA2924EE0441BBA8F8A235D8851B` |

两文件完整读取，执行前后hash不变。本review只写canonical本新文件，controller负责relay到原开发、复制到lane、后续stacked PR（base51）和hosted执行。未修改产品、测试、workflow或开发evidence。

## Findings（按严重度）

### F45-CI-1 — P1：job-level env 使用不可用的 runner context，workflow无法作为有效job执行

**位置：`.github/workflows/research-memory-settlement.yml:29–33`。**

```yaml
env:
  UV_PROJECT_ENVIRONMENT: ${{ runner.temp }}/research-memory-settlement-venv
```

这里的env位于`jobs.settlement-postgres.env`。该表达式位置允许github/inputs/matrix/needs/secrets/strategy/vars等context，不允许runner。runner.temp可用于获准的step级context或通过运行时shell变量取得；在此位置使用会被workflow表达式验证拒绝。

独立执行现有actionlint 1.7.12：

```powershell
& D:/AI/tmp/actionlint-1.7.12-windows-amd64-20260905/actionlint.exe `
  -no-color -shellcheck= -pyflakes= `
  D:/Code/citeframe-lanes/issue45-research/.github/workflows/research-memory-settlement.yml
```

实际 **exit1**，唯一报告：

```text
research-memory-settlement.yml:33:35: context "runner" is not allowed here.
available contexts are "github", "inputs", "matrix", "needs", "secrets", "strategy", "vars".
[expression]
```

本地直接执行Python正文会绕开GitHub表达式求值，因此正文120pass不能关闭这个workflow入口问题。

**最小修正／owner：** 原CI开发在同一workflow grant内，把runner.temp求值移到合法位置。例如在安装前的shell step用`$RUNNER_TEMP`写入`GITHUB_ENV`，供后续安装/执行步骤共同使用；或在两个相关step的env分别设同一`${{ runner.temp }}`路径。保留独立环境、frozen install、两个安装检查与后续no-sync；不更换uv、不改依赖/lock、不放宽测试。

**复验：** 新hash actionlint无错误，环境路径在安装和执行两步一致且仍为job-owned；hosted执行在后续delivery阶段独立记录。

### F45-CI-2 — P2：空理由的非strict XPASS可以被完成性guard判为成功

**位置：workflow:132–135，`RequireFullExecution.pytest_runtest_logreport`。**

```python
self.invalid |= not report.passed or bool(getattr(report, "wasxfail", False))
```

pytest的non-strict XPASS报告可以有`wasxfail == ""`。此时report.passed为True，布尔判断为False，nodeid也进入passed集合。全局`xfail_strict=true`可被测试marker的`strict=False`覆盖。

**独立实测反例**（仅自有TEMP fixture，未改真实产品测试）：

```python
import pytest

@pytest.mark.xfail(reason="", strict=False)
def test_one():
    pass
```

从冻结workflow原文AST提取未修改guard class，使用真实pytest执行上述单case；仅将root/expected_counts设为该临时fixture的一项，以独立测试guard。仍传`-o xfail_strict=true`、`--noconftest`、strict markers及no-cache。实际输出：

```text
X                                                                        [100%]
1 xpassed in 0.01s
exit 0
```

预期是exit1。当前120真实测试没有被这个探针替换，也没有证据表明当前120包含该XPASS；缺陷在workflow承诺的“所有xfail/xpass均拒绝”判定，可能在将来新增/修改marker时错误放行。

**最小修正／owner：** 在原workflow guard内判断`wasxfail`属性存在性，例如`hasattr(report, "wasxfail")`，不要以reason字符串truthiness作标记判据；保留非passed检查和原pytest非零状态。新增本地guard负例应包含空reason/省略reason的`strict=False` XPASS及普通xfail/xpass，全部要求exit1。无需产品/test文件、CI选择数或marker全局策略变更。

## 其他job语义审查

| 范围 | 本次结果 |
|---|---|
| 触发与权限 | **Pass，静态。** pull_request无base/path过滤，main push；contents:read；无continue-on-error、条件skip或非零状态忽略。适用于controller计划的base51 stacked PR；不代替PR实际执行或required-check配置。 |
| 服务与数据库身份 | **Pass，配置及本地正文。** postgres:17.11、独立固定测试DB、health check；正文要求psycopg、127.0.0.1:5432、指定DB、server_version_num=170011，连接失败不会skip。镜像版本tag固定但未声称digest供应链pin；本次未拉镜像。 |
| Python/依赖 | **方向符合grant，hosted未证。** setup-python3.12；`uv lock --check --python 3.12`后`uv sync --frozen --extra dev --python 3.12`；执行使用`--frozen --no-sync`。API manifest包含本套件使用的pytest、SQLAlchemy、psycopg及本地neutral包。F45-CI-1须先修正其env绑定。 |
| Own imports | **Pass，独立执行。** 六个own package roots逐模块检查；namespace所有search paths必须位于checkout root；tools、projection与fixture plugin有精确文件断言。前后两次检查避免只验证入口后混入外部模块。外来文件、外来namespace路径、空namespace均实际被拒。 |
| Pytest隔离与collection | **Pass，正常路径与已列反例。** 禁用autoload，明确native fixture plugin，`--noconftest`，清空addopts/pythonpath override。per-file 56/22/6/36、唯一nodeid、120总数、call-phase passing集合和所有report状态共同判断。不是只看收集数量。 |
| Skip/collect-only/deselect/omission/failure | **Pass，实际guard probes。** 详见下表。 |
| Xfail/XPASS | **部分失败。** 普通xfail/带理由XPASS被拒；空理由non-strict XPASS漏过，F45-CI-2。 |
| Baseline不依赖Git历史 | **Pass，源代码审查。** OLD_SOURCE内嵌、compile本地字符串；固定e7b3e86是provenance而非Git subprocess。boundary测试子进程只启动Python并使用本repo计算的路径。checkout无需full fetch。本review未重跑开发者的.git-free source-package65pass，不把该结果改署独立证据。 |
| Linux/frozen安装/hosted | **未执行／未接受。** developer本地uv权限拒绝保持真实缺口，本review没有调用或替换被拒uv。正文已有环境执行不证明Linux依赖解析/下载、服务容器或GitHub job。 |

## 独立实际执行证据

### A. 冻结inline正文＋新的真实PG

按原文定位`from collections import Counter`到heredoc结束，去除10个YAML缩进字符后compile/exec，正文未改。提取后的LF Python正文SHA-256：

`557840ACC4EF4A9A11F1260022A8F2355508832BE46A0D882D2EF10924D91283`

从lane根执行，已有只读工具：`D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -`，实际Python **3.12.14 Windows**。设置与workflow一致的own PYTHONPATH项（Windows用分号分隔），禁用bytecode/plugin autoload/cache并清空PYTEST_ADDOPTS。

新建reviewer自有PostgreSQL **17.11**实例，确认5432没有既有listener后，仅监听`127.0.0.1:5432`，使用独立`citeframe_issue45_settlement_test`与合成role `issue45_review`。CITEFRAME/AI_PDF URL均指向这个自有DB。正文允许该role差异，因为它验证driver/host/port/DB/version，不固定凭据。没有连接生产/开发者cluster。

临时cluster位于`$env:TEMP/citeframe45-independent-ci-20260929/data`；TEMP/TMP为本次自有`testtmp`，避免共享pytest目录权限冲突。initdb同前次出现restricted-token87/3诊断后实际成功exit0；同sandbox身份普通postgres启动成功，无提权或更换工具。未使用uv或执行frozen安装步骤。

执行提取方式：

```python
source = Path('.github/workflows/research-memory-settlement.yml').read_text()
start = source.index('          from collections import Counter\n')
stop = source.index('          PY', start)
body = '\n'.join(line[10:] for line in source[start:stop].splitlines()) + '\n'
exec(compile(body, '<exact frozen workflow inline>', 'exec'), {'__name__': '__main__'})
```

**实际：120 passed in 26.63s，exit0。** 这是完整原文inline的本地独立执行，含其PG版本preflight、120 collection/phase guard、前后own-import和fixture plugin校验。55个PGcase使用真实ORM建表，1个baseline case和64个非PG回归也完整执行。不是frozen install/Linux/container/hosted结果，不关闭F45-CI-1。

六个package实际import均在lane根下：API、Worker、backend-contracts、backend-persistence、research-persistence、memory-service；精确tools与memory_context路径亦在lane。未从canonical旧源码获得候选正文通过。

### B. 完成性guard负例

原class逐字从workflow AST提取，各case独立Python/pytest进程、独立TEMP fixture；仅测试root与expected_counts替换为相应临时用例集合。正式120 selection和产品测试从未修改。

| Probe | 实际exit | 要求exit |
|---|---:|---:|
| 完整成功正例 | 0 | 0 |
| runtime skip | 1 | 1 |
| collection skip | 1 | 1 |
| xfail | 1 | 1 |
| 带理由 non-strict XPASS | 1 | 1 |
| **空理由 non-strict XPASS** | **0** | **1** |
| call失败 | 1 | 1 |
| teardown失败 | 1 | 1 |
| collect-only | 1 | 1 |
| deselection | 1 | 1 |
| omitted selected file | 1 | 1 |
| zero tests | 1 | 1 |

**12项中11项符合，1项实缺。** 不能继承开发者11/11覆盖结论为所有XPASS情形都安全。

### C. Missing URL与origin负例

执行冻结正文前仅删除`CITEFRAME_ISSUE45_POSTGRES_URL`，实际捕获：

```text
SystemExit: CITEFRAME_ISSUE45_POSTGRES_URL is required; no PostgreSQL skip is permitted
```

字符串SystemExit对应非零终止，发生在engine构造之前。测试wrapper捕获该预期终止以断言消息；没有缺URL时悄悄运行非PG子集或skip。

随后执行原origin preflight，临时在sys.modules注入一个own-root名字的外来`__file__`、外来namespace `__path__`、空namespace三种情形，原verify函数均AssertionError拒绝；移除注入后真实namespace通过。这些是origin guard反例，不修改文件或native含义。

## 处置与最小后续

1. controller把F45-CI-1/F45-CI-2交回原开发，在当前workflow/evidence grant内修正。不要动已接受产品、测试、API锁文件或shared CI，不替换被拒uv。
2. 冻结新workflow/evidence hash交回本原独审。复验actionlint、空/省略reason XPASS、既有拒绝矩阵及inline；正常120执行和own imports保持。
3. 两项关闭后，可支持controller按base51进行stacked PR交付。hosted的Python3.12 frozen install、postgres17.11 service及实际120执行必须另有当前提交结果；本地正文不能代替。当前候选不应被标为workflow已接受或hosted green。

不存在因这两项CI修正而撤销产品C7E70C结论、重开schema或扩大runtime范围的依据。完整Research dispatch/reclaim、#43接口、同live-Attempt两次压缩、source/A1授权、模型/UI继续独立门禁。

## 保全与write-back

测试结束确认`remaining_review_schemas=0`，只对本次精确data目录运行pg_ctl fast stop并获得server stopped；启动命令正常结束。没有接触其他服务或UI46，没有模型/paid调用。

结束时workflow/evidence及原产品三文件hash均与用户pin一致：tools `F8E02EB6…0230A51`、tests `787ED87A…DC27E8`、产品evidence `F3021C39…39E1B6`。仅新建本canonical review；旧产品review、产品/CI/测试/evidence、Git状态、profile私有memory与共享workbench不变。临时PG/log/guard fixtures留在自有TEMP运行目录。沿用本session适用指令与只读bootstrap；本review为本轮唯一持久写回。
---

## 定向闭环复审 — 2026-09-29，候选 E17B81A4

**最新判定：BOUNDED APPROVE — F45-CI-1 与 F45-CI-2 均关闭。** 此判定更新前文旧候选的REWORK状态；旧finding和执行记录保留为历史。未发现此次两项修正引入的其他问题。支持controller将已审workflow纳入计划的base51 stacked PR；实际hosted执行及required-check配置仍是交付证据，不在本地批准中冒称完成。

### 精确候选及变更范围

| 文件（lane-relative） | 本轮前后稳定SHA-256 |
|---|---|
| `.github/workflows/research-memory-settlement.yml` | `E17B81A42BF72C9866F5958BA12310BCCF425EE4F29771FF6D83C91B0C6BC346` |
| `specs/v5/memory-management/evidence/issue45-settlement-ci.md` | `4A073B219B0CDBF33005A71378B11F155911F01CBED37F54150376811E9D53D2` |

两文件完整读取。独立在内存中逆向还原两项workflow修改后，原始bytes的SHA-256精确回到 `F77E6FF9ED5C41D4995092FEFC8B442BCB96D01C829178E6B72A96BC0FBCB6DB`。因此PG17.11/Python3.12、frozen安装命令、120选择和完整执行判定、missing-URL、own imports、权限及触发等其余正文未变；没有只依据开发者“仅改两处”的声明作判断。

### F45-CI-1 — 已关闭

job-level非法`${{ runner.temp }}`已移除。安装前新增shell step：

```sh
echo "UV_PROJECT_ENVIRONMENT=$RUNNER_TEMP/research-memory-settlement-venv" >> "$GITHUB_ENV"
```

RUNNER_TEMP在step运行时由shell读取，值写入runner的GITHUB_ENV供后续steps继承；该step位于`uv lock / uv sync`之前，后续`uv run --frozen --no-sync`无同名覆盖。安装和执行共享同一job-owned环境路径。引用的双引号保留路径空格，未改变依赖来源、锁或frozen/no-sync策略。

独立重跑既有actionlint：

```powershell
& D:/AI/tmp/actionlint-1.7.12-windows-amd64-20260905/actionlint.exe `
  -no-color -shellcheck= -pyflakes= `
  D:/Code/citeframe-lanes/issue45-research/.github/workflows/research-memory-settlement.yml
```

**实际exit0，无diagnostics。** 这是actionlint的workflow/context验证；shellcheck、pyflakes明确关闭。shell环境继承语义由静态审阅核对，本轮没有执行GitHub runner、uv或安装步骤。

### F45-CI-2 — 已关闭

原truthiness判断已改为`hasattr(report, "wasxfail")`，不再依赖reason字符串是否为空。独立从**当前冻结workflow** AST提取原class，使用已有API Python、真实pytest报告和自有TEMP fixture做5项定向检查；只为probe绑定root/expected_counts，未修改真实120选择或产品测试。

共同pytest参数包含`--noconftest --strict-markers -p no:cacheprovider -o addopts= -o pythonpath= -o xfail_strict=true -q --tb=short`；plugin autoload/bytecode关闭，PYTEST_ADDOPTS为空。每项在独立Python子进程执行，另一个observer只打印实际call report，不伪造report或修改guard。

| 真实probe | 实际call report | 实际exit / 要求exit |
|---|---|---|
| 普通通过 | passed=True；无wasxfail属性 | 0 / 0 |
| `xfail(reason="", strict=False)`且通过 | passed=True；wasxfail存在且为`''` | **1 / 1** |
| `xfail(strict=False)`且通过、省略reason | passed=True；wasxfail存在且为`''` | **1 / 1** |
| 带理由non-strict XPASS | passed=True；wasxfail='probe' | 1 / 1 |
| 普通xfail | passed=False；wasxfail='probe' | 1 / 1 |

**本reviewer 5/5独立定向probe符合预期。** 空/省略reason两项均实际输出`1 xpassed`，同时guard强制exit1；正常通过仍exit0。开发者13项矩阵仍归开发者，本轮没有将其重新署为reviewer执行，也没有重复未改变的产品/PG整套。

### 受保护对象与证据边界

本轮独立重算以下hash，与此前pin一致：

| 对象 | SHA-256 |
|---|---|
| 产品tools.py | `F8E02EB6C9F93DED10BF59C9B136168130591FC49B4DED0041E6115530230A51` |
| settlement专项test | `787ED87A226F26D928C2F7505A444235F4EB658E9C252719956FFAB5F9DC27E8` |
| 产品settlement evidence | `F3021C394463BB9FCC0F8255F37EADA1EEFBF899C135EE633ED92561F939E1B6` |
| shared `.github/workflows/ci.yml` | `363F81520750D14E74091D97CF63DC37194E9281A69DCBEE168F171C2CE8A2FD` |
| `apps/api/pyproject.toml` | `17A546289BAD50C1C07BBF315CEA01292140DE70A36BF453E2F21FC5DE9FB115` |
| `apps/api/uv.lock` | `F68143541ABFFDE4AF5F61F63EA2293E7EE5AC7E5150BF61A5DF58B3745C6CF0` |

前文独立 **120 passed in 26.63s** 仍属于旧workflow候选F77E6FF9的inline执行。它支持未变化的基础机制，但本轮不将其改称E17B81A4整套执行或hosted green。新候选本轮证据仅为精确两项差异核对、actionlint、5项真实guard probe及受保护hash核对。

没有launcher、uv、network、PG/service、模型或UI调用，没有绕过此前拒绝。未重跑产品120或PG套件。产品C7E70C审查不变，Alembic/未来schema、#43ABI、planner/reclaim、完整Research runtime、同live-Attempt两次压缩及语义/UI仍在各自门禁。

### 写回与交付

仅向本canonical原CI review追加本节；原review正文、产品/测试/workflow/evidence、sharedCI、manifest/lock、Git状态、全局私有memory和共享workbench均未修改。自有TEMP只生成定向guard fixture；无后台服务或probe进程遗留。

controller可据上述两个新hash继续base51 stacked PR提交和后续hosted校验。若workflow发生后续变更，需要按新hash界定复验范围；当前两项finding已闭环，不要求重复无变化产品审查。