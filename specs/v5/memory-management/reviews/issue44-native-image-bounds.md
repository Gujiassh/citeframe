# Issue44 R5 native image bounds — independent Critical contract review

Date: 2026-09-29. Reviewer: original #44 independent reviewer. **Disposition: REQUEST CHANGES for the complete resource/activation contract; bounded arithmetic/source-read primitives are design-eligible after controller assigns the exact leases below. No product write grant or runtime acceptance is issued here.**

Reviewed candidate: `lanes/issue44-native-image-bounds.md`, SHA-256 **FAE4D6588D98FB339FCB46D866956D993C989AC2365F387F4C9107375BC71F68**, unchanged throughout. Worktree `D:/Code/citeframe-lanes/issue44-provider`; observed HEAD **7d6be8a236d48135460b0a5677b6ea01edd31b4f**. Prior PR52 builder approval remains intact. Hosted successes/external failures are controller-reported context, not image-resource evidence or a merge waiver. No provider/profile re-audit was performed.

## 1. Governing goal and direct acceptance oracle

有效spec v4 §§12–14/A1选2仍要求同问题任务内的完整工具续轮、问题后重复压缩、原始来源/冻结预算/效果身份不变；shared prompt/tool/history/checkpoint/planning/SSE/log/final output不得接收任何私有内容，包括请求者自己的私有内容。本slice为真实native图像准备的资源前置条件，不能替代这些目标。

本合同应交付的直接结果：合法旧输入在受控source-read/decode/render/encode/IPC/parent生命周期内，保持旧PNG字节、geometry、target/region/retrieval顺序和detail；不合资源或授权条件的输入在对应消耗前安全拒绝，取消/失效不采用任何部分结果。新子进程输出安全子集可作为未激活实验，不等于完整legacy parity。

- 单纯限制最终GenerationImage字节无法保护更早的下载/解码/渲染；候选正确识别了这一点。
- Linux-only可作为本轮工程验证环境；Windows算术/序列化测试不能证明Linux RLIMIT/timer/kill。不得把未测限值当生产背书。
- 8张输出相对原64张explicit上限、拒绝旧downscale PDF、optional retrieval从soft-skip变为错误均是真实行为差异；激活前须恢复相应能力或取得明确产品约束变更批准。

## 2. Findings（按风险排列，返原developer/owner）

### F44-NI1 — P1：child slot没有界定parent已返回结果的占用生命周期

**位置：§3表与57行；§4 signature/budget；§8后续base64边界。**

候选限制同时准备一个admission，但函数返回`tuple[bytes,...]`之后，结果仍会被chat、base64字符串和serialized request持有。没有规定该slot/字节reservation何时释放或转移，所谓“later chat admission/request budget”也没有当前可消费接口。即使只有一个API进程，每次串行准备返回后允许下一个admission，多个并发chat仍可持有任意多个16MiB结果。2GiB部署限制只能最终杀进程，不能代替image admission的可用性边界。

实际`services/chat.py::_build_generation_user_message`先持有原image bytes，再生成base64 bytes、ASCII string及data URL；后续payload/archive/HTTP序列化还可能复制。每admission的16MiB不能被写成整个parent仅保留16MiB。IPC分块list→join/bytearray→bytes也有瞬时副本，当前未纳入明确上限。

**最小修正：** 明确区分child并发slot和parent retained-output reservation。由同一可信native composition从prepare前持有字节/数量reservation，覆盖接收缓冲、返回原bytes、base64/请求/archive复制和消费结束，成功返回不能自动释放；错误/cancel/revocation/最终消费者清理才释放，必要的ownership转移必须明确。可以用既有caller budget作用域或小的局部reservation，不需要通用resource service。为同一API进程定义最大同时保留总量，跨worker按实际worker数计入部署上限；无界等待队列继续禁止。

**oracle：** 第一个结果仍被消费者持有时反复准备第二/第三个结果，必须在新分配前按全局余量拒绝；释放原结果所有受控副本后才能恢复。测试bytes/base64/接收转存峰值、异常清理、重复释放、调用结束但consumer尚未结束，不能只测同时child数量。未接入consumer前可在专用test作用域验证，但不能声称parent全生命周期已经安全。

### F44-NI2 — P1：`python -I`不覆盖startup内存、site代码和继承凭据；启动早期parent死亡未闭合

**位置：§3 child memory/wall；§5第88、96行。**

候选在脚本进入后才安装RLIMIT/timer。Python interpreter/site初始化发生在这之前，父进程的monotonic timeout只限制等待时长，不能回溯限制startup期间的地址空间。`-I`也不清空环境或关闭site处理。

**独立实际探针：** 本地Python3.12用`-I -B -c`启动，只增加一个合成环境marker，结果为`isolated=1, site_loaded=true, synthetic_env_inherited=true`。没有读取真实凭据。说明不应以-I推导“stdlib-first直到OS限制”或“只经pipe传入所需storage凭据”。若启动期parent死亡，脚本timer尚未安装，也没有已规定的parent-death机制。

**最小修正：**
1. 明确受审的启动序列：考虑`-I -S`禁用预先site处理，安装限制后再加载固定解释器/镜像的受审依赖目录，不执行任意.pth/sitecustomize，不用用户PYTHONPATH。若保留site，必须列明实际启动依赖并提供独立的启动前资源保护，不能声称脚本内512MiB覆盖它。
2. 明确startup的硬memory envelope来源：已验证的部署级limit或受审的pre-exec/launcher机制；不可在多线程API中随意采用不安全preexec_fn，也不能由此擅加容器/依赖。512MiB在script entry后才生效的事实需如实记录。没有已授权启动保护时，parent/child supervisor的生产界面继续禁用。
3. 显式child环境allowlist、`close_fds`/必要pipe FD白名单、固定owned脚本路径、无shell；不继承整个API环境中的DB/model/其他服务凭据。storage snapshot字段repr=False，密钥只驻留所需进程/pipe，不放错误或metadata。声明并验证core-dump保护，不能默认native codec崩溃不会持久化含凭据内存。
4. READY须确认限制有效，早期parent死亡、READY前超时、control接收期死亡均有有界退出策略；进入codec前安装默认动作timer且验证信号mask不阻塞。不能依赖Python线程在native GIL占用时运行。无法reap时保留占用、停用后续image child，不把slot当成可重用。

**Linux真实oracle：** startup前/后各阶段超时与parent-death、env/FD隔离、site无提前重依赖、RLIMIT实际拒绝、native GIL占用时kernel timer终止、core-dump策略、kill/reap失败隔离。当前Windows设计探针不证明这些。新增Linux job/镜像配置仍须controller/部署owner另批，当前没有该租约。

### F44-NI3 — P1：bounded chunk不等于bounded pipe等待，IPC状态机与reservation回收规则需落定

**位置：§5第88、94–96行；§3 30s总deadline/1s teardown reserve。**

只写“64KiB chunks under deadline / bounded pipe IO”不足以保证cancel/deadline。子进程发送一个合法length后只写1字节并停住，父进程阻塞`read(n)`就无法按monotonic deadline检查取消；control frame写入一个不读stdin的child也可阻塞。旧publication的poll→pickle recv模式已被正确排除，但替代的可执行I/O策略尚未规定。

**最小修正：** 父进程用Linux nonblocking fd + selector/poll的有界read/write状态机；每次partial I/O都检查同一absolute monotonic deadline、cancel和child exit，控制写入/READY/result读取/EOF/退出等待共享预算，teardown余量不可重复花费。无需通用IPC框架。给出最小版本化frame规则（长度字节数/端序、READY/control/result/terminal顺序、frame count、aggregate byte cap），验证长度再分配；拒绝重复/缺失/额外ordinal、source identity错配、尾随frame、伪成功/exit非0及任一partial frame。父端只做有界header/digest/metadata核对，不能为验证结果重新无界解码。

每对象/每页reservation要说明失败时的保守收费：被kill或无完整charge receipt不能推定“没读字节”而退款。§3“同immutable object只读一次”与§4“不同PDF page可重读并收费”要统一成明确cache/batch key和实际source-op计数；不可把重读隐含为免费。

**oracle：** child不读control、只写1字节、谎报超大长度、合法单帧但累计超限、写满pipe、重复ordinal、EOF前后卡住、exit0但不完整、成功frame后不退出、取消发生在每个阶段。父进程返回/终止时间与峰值内存都实测；没有遗留reader线程/child/slot。不需要source/DB接口即可实现和测试该局部协议，但先补上述小合同。

### F44-NI4 — P1 activation gate：旧PDF final-transform可预计算，8张硬截限也拒绝资源很小的旧合法输入

**位置：§1 supported subset、§3 output8、§7拒绝downscale、§9 recommended first slice。**

合同诚实标记了subset，但尚未规定恢复原目标的必要路径；应把可计算的旧final transform优先纳入实现路线。普通A4/Letter完整页会走原downscale，不能长期用“unsupported”替代原证据输入能力。

**本reviewer实际可行性证据：** 在当前锁定版本PyMuPDF1.28.2/Pillow12.3.0，以原`crop_pdf_regions_png`函数AST作old oracle；原helpers与所有PDF均在内存，未导入应用/DB/配置。针对300×400、595×842、612×792三种page、0/90/180/270 rotation、正常/offset cropbox、full/fractional region，合计**48组PNG逐字节相等**。其中**8组走旧downscale**，候选实验没有分配first150dpi pixmap以发现尺寸。

可行顺序：在受限child中构造native displaylist，按当前安装库的`fz_bound_display_list → intersect clip → transform150/72 → fz_round_rect`得到原first raster bbox；若longest>1280，计算原`scale=1280/float(longest)`并使用**原第二次调用的同一matrix顺序**，先对final bbox/stride/编码峰值reserve再只render一次。否则保留原`dpi=150`调用。displaylist本身仍需hard memory/CPU/wall限制，几何计算不使parser安全。

A4全页实测：推算first1240×1755，单次final905×1280，PNG DPI=96×96（原matrix分支默认值），SHA-256 **77F9C52A0BDD005C3745B343AFC2CBA838544A1B084B11C29B38D4C903671B88**，与old output逐字节相等。非downscale分支必须继续150dpi；统一改成dpi或统一matrix会改变PNG metadata。此探针证明有真实工程恢复路线，不是对所有PDF/平台的普遍证明；UserUnit/复杂bbox/annotations及Linux pinned build还需对应原函数oracle，原符号属于库内部也必须版本锁定。

另一个实际反例：用原`_crop_canonical_image` AST对32×32 canonical RGB PNG，按8 targets×8 regions生成**64张PNG，总共5120 bytes**。这属于旧schema和crop逻辑可处理的极小输入，候选8张cap却在GET前拒绝它。不能把此拒绝描述为旧能力保持。实际还允许最多4张可选retrieval图。

**最小修正/激活条件：**
- 初期subset仅作未接入的测试里程碑，文稿补充old-final-transform的明确交付与byte/geometry/DPI oracle；优先实现常见downscale路径，旋转/offset等逐项证明，不凭视觉相似度或无依据“无法计算”永久排除。
- 保留64 explicit及原optional4的语义基线；按实际source/decode/finalbytes/CPU预算进行有界串行batch，而非用无测量8张cap替代。可以对真正超预算输入安全报错；若产品确要降低数量/支持平台/格式，需明确独立批准和用户可见验收，不能通过内部contract默认完成。
- 当前提案数值只用于实验，未来任何生产限值需测量与部署批准。不能为达到旧count而直接抬高全部内存预算。
- retrieval的soft-skip→selected failure传播也是产品语义变更，必须原native owner逐项映射safe error、取消与事务回滚；不改mode1即时/SSE或mode2 provisional时序。UI46没有操作授权，本review不执行或批准UI。

### F44-NI5 — P2，resolver接入前：tuple bytes不足以承载geometry-only与完整source/result对应关系

**位置：§4 return/source fields；§7 include_image_payloads=False；§8与§9 extraction/injection。**

实际PDF resolver即使不输出图片，也调用`_page_geometry`并持久化cropbox/rotation/display dimensions。当前提议source仅含page_number等，`prepare_native_images -> tuple[bytes,...]`没有geometry-only结果、逐source状态/charge receipt或输出ordinal对应数据。若接入者仍在parent调用旧`_page_geometry`补资料，会重新引入无界fitz.open。PNG expected geometry也不能在canonical来源上随意optional而绕过旧比对。

**最小修正：** 明确API-local的source-kind必填字段、region/ordinal唯一性和geometry-only操作；返回一个小的局部结果记录或已约定的独立bounded geometry结果，能将page geometry、ordered PNG bytes/width/height/digest、source identity与实际/保守charge对应起来。来源ref沿用parent原owner记录，不让child凭空授予authority。不要声明/导出第二个#42 GenerationImage或通用content-part协议。接入前证明include_image_payloads=False从未在parent重新打开PDF；成功的空geometry-only输出不误判为漏图，真实crop缺失仍拒绝。

## 3. 可保留的设计方向与授权边界

- **PASS，方向：** 单用途、短生命周期codec child；source留child、无pickle/unbounded communicate；bounded GET真实字节+hash验证后decode；PNG header先验；PDF parser也进child；资源错误不采用partial explicit结果；不修改已有publication storage语义。
- **PASS，方向：** snapshot由原storage owner从既有设置生成，object_key不能选择endpoint/bucket；MinIO/PoolManager TLS与retries=False沿用实际构造语义。第一阶段只用合成/本地fixture，不访问现有MinIO/DB/真实凭据。
- **PASS，权限分层：** helper只消费trusted native来源，不把object_key当授权。parent先验证整个现有workspace输出受众，私有source全部排除；source eligibility/version在adoption及下一次dispatch由原owner重验。需要明确这些检查与后续消费的原子/版本绑定，resource helper测试不会兑现授权撤销的集成保证。
- **BLOCKED，production：** caller尚未消费实际#42 image ABI和#43有效授权/生命周期接口。#42正审ABI、#43只做I3/I4不构成本lane修改它们的授权。本review不关闭其残留或扩大任何owner租约。
- **NOT RUN：** Linux真实RLIMIT/timer/startup/kill/core测试、deployment worker/cgroup测量、真实storage/DB/transaction和UI。这些没有可用实现可验收，本轮不会用mock setrlimit宣称PASS。

## 4. 最小可实施slice与文件租约判断

**现在没有新增产品/依赖/容器写权限。以下是controller可考虑授予原owner的最小范围，不是本review代发租约。** 不整体等待#40/#43。

### A. 可先授予：无激活、无进程launch的真实算法/读取原语

- 原native developer：NEW `modalities/native_image_bounds.py` +专属`tests/test_native_image_bounds.py`中的strict envelope/source/region校验、累计reserve算术、capped sink/frame parser、旧PNG Decimal crop和PDF final-transform计算的真实fixture测试。仅局部函数，无空实现wrapper/framework。
- 原storage owner：NEW `services/native_image_source.py`的受审frozen snapshot形状、实际MinIO/urllib3构造语义与bounded response reader；使用injectable synthetic response测试length+1、假Content-Length、hash/close/release。parent snapshot factory惰性读取既有settings，child读取部分不得import settings/ORM；不改storage.py/publication行为。
- byte-parity测试直接以原函数/源AST作为oracle，不从新函数复制expected结果。此时不存在生产调用者，原legacy代码不删；实际extraction/wiring时再由原owner一次性移除被替代重复body，不能长期保留两套active crop算法。

上述真实算法和字节读取原语不依赖尚未决定的process IPC/部署启动机制，可以继续推进。所有候选constants标为实验，不创建生产配置文件。

### B. 仅待NI1–NI3小合同：真实Linux进程resource harness

- NEW `modalities/native_image_child.py`与bounds中的监督代码，加同一专属测试；补齐launch、retained-output reservation、nonblocking IPC、deadline/cancel/reap后才实现对应接口。
- 真实Linux tests必须验证内核资源限制，不mock OS限制来代替；Linux执行环境/CI由controller和部署owner先授予。没有容器/manifest/依赖变更授权，若需要这些才可取得startup envelope，须把精确delta交原owner决定。
- 一个child/一个source操作的合成read→codec→framed transfer可以作为可独立接受的工程slice；通过时结论明确为未激活resource harness，不宣称native全流程或full legacy parity。

### C. 仍需独立批准的后续租约

- `image_evidence_targets.py`、`pdf_evidence_targets.py`、两层evidence_targets：NI5局部结果/geometry接口、完整源/版本授权边界以及原函数提取/parity先审后接入；保持无界ImageBytesLoader仅属于未迁移旧路径，已启用bounded路径不得回退到它。
- `visual_enrichment.py`、`services/chat.py`：parent retained-output总账、explicit/retrieval同admission、选中资源失败语义、旧ordering/detail、事务和取消必须一起验收；现有router/deps没有本slice写权限。
- shared GenerationImage/exports/image counting依旧#42唯一owner；#43仅消费其获批范围。没有ABI副本、新schema或owner替换。
- Full activation还需NI4恢复矩阵、Linux pinned库实测、部署真实limits/worker count、source撤权/当前版本及native事务测试、后续provider image accounting。UI走查交#46的未来明确授权，本轮不碰其已拒操作。

## 5. 实际证据与复现边界

本轮只读实际storage process/client、image/PDF resolver/crop、visual_enrichment、chat图像拼接、schema maxima、Worker canonical PNG产出、Dockerfile/compose overlay及测试fixtures。canonical ingestion明确convert到RGB/RGBA、清metadata、PNG encode；这是初期PNG模式选择的事实依据，仍不能免除像素/字节/CPU限制与旧存量数据检查。

| 实际文件 | SHA-256 |
|---|---|
| services/storage.py | `6FCBB3F57D7E6198E420886EA3B74858E07A5E0652CF04674596A8FBA15EFD95` |
| modalities/image_evidence_targets.py | `80A1915CE56EA42CDFB1963724BD5918017274686E8942AC55CCFAE127A26EF7` |
| modalities/pdf_evidence_targets.py | `9EC66A868D963FAD94ECD594F07D418C5A501B785CEFE7E63DB35351453D3229` |
| modalities/evidence_targets.py | `008F5FFD4B85FC30B1E8B2E601E0E2F0B65087749CC0C1A20CB22D06A1B59FAF` |
| schemas/chat.py | `71857732FF3245AF5E0CEF4180A64CF3E6A968CBD6B174B60222699ACDBFEB67` |
| infra/docker/Dockerfile.python | `52FBD1C93D960FCEAF230FE935CA51D3988E98AEF91D3EC75524B8DD0F5CA113` |
| infra/docker/compose.m403a.yml | `CA54C999F7400D2CCE52F8D0A4A593CC49159FEC6D86DEF4654ADCAA11E56ADF` |

前三类相对apps/api/src/ai_pdf_api。实际hash与candidate source表一致，未把旧快照当新代码。

独立inline实验解释器 `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -`，当前真实库PyMuPDF1.28.2/Pillow12.3.0，与API lock相符：
1. AST提取原crop函数与必要纯helper，无API/settings/DB import；内存构造受控小PDF，old实际两次render输出与预计算final-transform的一次render逐byte比较，48/48通过。此为Windows锁定库的可行性证据，Linux parity仍须测。
2. 原canonical crop生成64个tiny PNG，合计5120 bytes，展示8输出cap的真实兼容影响。
3. `python -I`的site/env合成marker探针。只读取自己注入marker，未读取/输出真实secret；没有启动candidate child、实际Linux limit或source GET。

未对不存在的实现给runtime PASS。NI1/NI3的失败场景是明确合同反例和后续测试oracle，不伪装成已执行的candidate故障。未做paid/live模型、外网、服务/DB变更或UI46操作。

## 6. 最终交付

**REQUEST CHANGES：NI1 retained-output生命周期、NI2启动/凭据隔离、NI3可取消有界IPC需原developer小范围重写；NI4 legacy恢复与NI5geometry/result合同分别作为activation/integration门槛。** 算术、bounded reader、真实旧final-transform和PNG parity原语可在controller授予相应新文件后独立实施；不以整个runtime未齐为由停止它们。

本review只创建本文件，未改候选或任何产品/测试/依赖/容器/Git/其他review。write-back保存在指定artifact；无private-memory/shared-workbench写入。候选hash复核不变，旧provider/profile/builder的所有closure不受影响。Controller负责原owner返工、文件租约和提交交付。


## Targeted §12 geometry-contract recheck — 2026-09-29

**Disposition: ACCEPT — exact §12 geometry-only implementation contract. No blocking finding in this two-file small contract.** 根据controller现有条件授权，原developer现在可开始且仅写：

1. NEW `apps/api/src/ai_pdf_api/modalities/native_image_geometry.py`
2. NEW `apps/api/tests/test_native_image_geometry.py`

不等待launcher、#43或完整R5。该结论批准清楚界定的数值算法及其测试实施；不是尚不存在代码的ACCEPT，也不是Linux/kernel/full legacy parity验收。原provider/profile/builder无需重审。

### 精确身份和范围

- 本次完整读取修订合同，优先审§12签名、数值域、旧函数oracle与两文件租约。候选SHA-256 **074C4E95490E190257943C9F1102C54246FFDF88D5C60ADA374FA27779EC7B97**，审前/审后不变。
- HEAD仍为 **7d6be8a236d48135460b0a5677b6ea01edd31b4f**。当前尚未出现native_image_geometry产品模块；本review没有创建它。
- 原review追加前SHA-256 **A25EEFC8A4EDFBDD6DCBF0014821A66D7FCAB8B5C4BD13ADD1F7C1E6D0CE0E5F**；历史字节前缀完整保留。
- 再次验证旧oracle source未变：image_evidence_targets.py **80A1915CE56EA42CDFB1963724BD5918017274686E8942AC55CCFAE127A26EF7**；pdf_evidence_targets.py **9EC66A868D963FAD94ECD594F07D418C5A501B785CEFE7E63DB35351453D3229**。
- 当前目标仍为v4/A1选2完整共享任务与原始来源语义。保留**64 explicit + optional4**；不把新算术domain、实验资源常数或Linux-only试验解释成已批准的产品输入缩限。

### §12逐项判定

| 条目 | 独立判断 |
|---|---|
| 签名和职责 | **PASS。** png_crop_bounds只接收维度/region；pdf_render_plan只接收cropbox、真实display-list numeric bounds和region；局部冻结PdfRenderPlan只回clip/bbox/matrix/dpi。无bytes、page/document handle、loader、source DTO、budget、dispatcher或授权对象，不产生#42 ABI副本。 |
| 严格数值域 | **PASS。** strict int/float与bool/subclass拒绝、tuple arity、finite、normalized region和安全rect domain明确。实际SpatialRegion为float字段，并用x+width/y+height≤1验证；合同的数值比较及合法0/1归一与该入口相符。±1e6 points/2^31−1仅为本算术接口边界，不是模型/生产资源cap。 |
| PNG baseline | **PASS。** Decimal(str(...))、原floor/ceil/clamp、empty规则明确；使用固定本地默认Decimal context，不能继承调用者的precision/rounding/trap变化。无resize/颜色/encoder变化。 |
| PDF branch与舍入 | **PASS。** 真实display-list bounds、native FzRect交集、150/72 transform、fz_round_rect及旧matrix乘法次序明确；不以额外安全ceil margin选择旧分支。保留bbox origin与精确width/height，最终matrix tuple不经额外舍入。 |
| No-first-render | **PASS，合同可实施。** 模块/函数不接受PDFbytes或handle，不调用open/get_displaylist/get_pixmap；只允许PDF调用时lazy import pinned PyMuPDF的常量尺寸几何运算。display-list获取仍由未来受限caller承担，算法自身不证明parser安全。 |
| 错误与依赖 | **PASS。** 三个固定local ValueError code、无raw input/error泄漏；未知库版本/必要symbol不可用只影响PDF调用，PNG和模块导入不依赖PyMuPDF已加载。没有新依赖或shared ProtocolError。 |
| 旧行为oracle | **PASS。** source-hash-pinned AST提取旧函数，真实Pillow/PyMuPDF同一fixture对比bytes/bbox/DPI/order，不用新实现输出充当expected；unknown/missing依赖必须显式失败。 |
| 实际实现/Linux/full parity | **PENDING，不在本批准内。** 代码尚未交付；Linux/complex输入/owner消费仍是实际验收门槛。 |

实现时测试应遵守这些已明确含义，不需要额外wrapper：
- planner的branch为longest≤1280用dpi150、否则原matrix且dpi=None；旧matrix分支PNG metadata为默认96dpi，不能混用。
- display_list_bounds取同一page的真实display list，沿用旧get_pixmap默认annotations=True。测试“annotations on/off”应覆盖有/无annotation fixture；不能给旧oracle强加annots=False后称旧默认parity。
- PNG需隔离完整本地Decimal context；altered ambient context的测试还应防止继承异常trap导致合法输入失败。
- invalid/empty/engine_unsupported各自固定code；特殊值不得由任意__float__或对象coercion引入native计算。
- Test rendering只针对明确小的synthetic fixtures；planner自身的禁止render/open instrumentation与fixture允许render的作用域须区分。64 tiny输出不意味着提高当前资源常数，optional4/order在后续消费仍保留。

### 独立证据：沿用48矩阵，并核对新tuple接口没有改变算术

原review的48 old/new byte-parity案例（含8个downscale）及64张/5120bytes PNG实验保持原证据归属，不记作developer新执行，也未重复把它宣称成Linux结果。

本轮另用本地Python `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -`、实际PyMuPDF1.28.2进行**4个小接口探针**：A4、offset cropbox、0/90旋转、full/fractional region。旧函数AST直接渲染作oracle；候选计算实验只传`tuple(cropbox)`、`tuple(display_list.rect)`与region，以native FzRect恢复numeric bound、将final matrix序列化为六元素tuple再构造Matrix。**4/4实际PNG bytes及pixmap bbox相等**，说明§12的数据边界保留已有恢复路线，不必向函数传page或display-list handle。

另独立检查固定`Context(prec=28, rounding=ROUND_HALF_EVEN)`中的Decimal计算在外层precision3/ROUND_FLOOR时结果不变；受控样例边界为265121435/768852147。此为接口数值语义可行性探针，不是新产品函数通过测试。

实际old-oracle、fixture-only render及tuple重建均只在内存中执行，无API/settings/DB/source授权导入，无产品文件生成。没有Linux RLIMIT/timer/launcher测试，也没有声明所有复杂PDF已经parity通过。

### NI1–NI5修订的design层状态（不扩大当前租约）

- **NI1：设计修正方向接受，实施/测量未关闭。** child slot与retained-output lease已分开，成功返回不释放、copy envelope和no-escape要求明确。256MiB/R公式/lease状态仍是待测提案，不批准生产常数、lease manager或consumer wiring。
- **NI2：保持独立deployment gate。** 文稿承认-I不足，并提出native launcher→-I -S、pre-exec限额、PDEATHSIG/env/FD/core策略；这是新native launcher/build依赖请求，**未获授权，本review不批准创建tools/native-image-launcher.c、build/copy/镜像/依赖改动或supervisor实现**。主控上报和后续owner决定仍需精确单独批准。它不阻塞§12。
- **NI3：设计修正方向接受，真实Linux IPC证据未关闭。** nonblocking selector、同一deadline/teardown、明确frame顺序、EOF+exit0、ordinal/receipt校验和失败全额收费已回应原反例；不由此授予frame parser/supervisor/source reader文件。实际实现与内核测试仍待其独立scope。
- **NI4：原产品目标偏离在文稿层已纠正。** 明确保留64+4，常见downscale是必需路径，48矩阵为起点；已撤回永久8张cap和常见PDF排除。**full legacy parity仍待新代码独审及Linux/complex矩阵**，现有annotations/透明度/UserUnit等未测不得自称通过。
- **NI5：局部geometry-only/source-result对应关系在设计上回应了缺口，但source/result DTO及resolver integration未授权。** 当前只允许§12的无source身份算术PdfRenderPlan；不实施§4的NativeImageSourceRequest/PreparationResult/Charge，也不复制#42共享image ABI。

既有source权限、撤权/取消、共享全部读者、native事务、#42 ABI及#43 I3/I4均由原owners继续负责。当前几何算法不获得或改变这些权限。optional retrieval仍保留原soft-skip基线，未来资源失败分类另由native owner审；本轮不接触UI46。

### 实施handoff与下一次验收

**原developer可以立即按已批准§12写上述两个新文件，回报精确code/test hashes及实际测试证据给本原reviewer。** 可完成PNG bounds与PDF final-transform真实算法、受控fixture oracle、strict negative/import/no-render tests；不要创建空壳dispatcher或顺带实施loader/sourceDTO/native launcher。

第一轮代码验收将检查实际实现而非仅计数：旧hash oracle、48矩阵和复杂小fixture、64crop/order、bbox/DPI、固定Decimal context、safe错误、lazy依赖、planner零render、无产品caller。Linux重跑与未来CI收集要由controller另行提供授权；当前没有CI/lock/依赖文件租约。Windows通过只能报告其平台证据，不能预先宣布Linux/kernel/full production parity完成。

本次仅追加原review，候选合同只读、hash稳定；未改产品/测试/其他review/ABI/schema/依赖/容器/Git，无provider/model/DB/service/UI操作，无private-memory/shared-workbench写入。没有创建重复实施owner。§12 **ACCEPT** 与其他未批准resource/activation gates分别成立。


## Independent geometry implementation acceptance — 2026-09-29

**Disposition: ACCEPT — exact §12 two-file numeric implementation, with independently observed Windows parity. No blocking implementation finding in this bounded slice.** 原developer可将当前冻结的两个文件交由controller按其权限提交；本结论不授权launcher/build、source loader/DTO、dispatcher、resolver/default activation或任何UI操作。完整R5资源隔离和activation仍保留前文未关闭门槛。

### Governing goal and exact candidate

再次对照spec v4目标、§13/A1选2和已接受§12：同任务工具续轮/每次dispatch前压缩、原始来源语义、共享所有读者的权限边界继续有效；共享上下文及派生链路排除全部私有数据。当前数值函数不接收source或权限，不改变这些规则，也未验证其消费端。几何算法的直接验收oracle为同一真实旧函数与候选计划产生相同PNG bytes、bbox、DPI和crop顺序，且候选planner不打开/渲染文档。64 explicit + optional4目标保持不变。

Worktree: `D:/Code/citeframe-lanes/issue44-provider`; read-only verified HEAD **7d6be8a236d48135460b0a5677b6ea01edd31b4f**, branch `work/issue44-chat-runtime`。以下是当前工作树未提交candidate的原始文件SHA-256，不将HEAD当作已包含新代码：

| Candidate | Exact SHA-256 |
|---|---|
| apps/api/src/ai_pdf_api/modalities/native_image_geometry.py | `62B89093C67B88B16CB926C61A4DC1FC3725341332350B32BD88FFCA4532368C` |
| apps/api/tests/test_native_image_geometry.py | `538AB2C3575E04EDC66BBC2DBC43A573DE05BCB9B07B3598CCADB902FA3B25F2` |
| specs/v5/memory-management/evidence/issue44-native-image-geometry.md | `FB875C5A7A4FAD3AFCD8309914D33C993DBB039389F9AAF85B14FC05E37CE6B5` |
| specs/v5/memory-management/lanes/issue44-native-image-bounds.md | `074C4E95490E190257943C9F1102C54246FFDF88D5C60ADA374FA27779EC7B97` |

原review追加前SHA **9AD4D73D3D962A94CCC93BB284F96297F165C1A9C184E2D466E9C0B01F9A57D0**。本节使用append保留全部历史字节。开发和controller在evidence中的119结果仍分别归属其执行者；以下结果为原appointed reviewer本轮实际独立执行。

### Implementation judgment

| Review area | Judgment and direct evidence |
|---|---|
| Contract / scope / architecture | **PASS。** 两个函数及冻结PdfRenderPlan与§12一致；单一数值职责，无bytes/page handle/source/authority/counter/budget，无shared ABI或新框架。当前没有production caller。 |
| Strict numeric boundary | **PASS。** `_coordinates`拒绝非exact tuple、wrong arity、bool、数值子类、custom coercion、非有限值和超大int转换；维度为strict int 1..2^31−1，rect为finite/increasing/abs≤1e6。region沿原float sum比较，输入先验证再归一，不把无效数值clamp为合法。边界是算术域，不是生产容量。 |
| PNG / Decimal | **PASS。** 与旧`_pixel_floor/_pixel_ceil`相同Decimal(str(float))、floor/ceil和clamp；显式完整Context隔离precision/rounding/exponents/flags/traps。实际RGB/RGBA bytes/order和独立随机算术对照通过。 |
| PDF / old branch | **PASS。** 同原cropbox-relative clip及0.5pt检查；使用真实display-list numeric bound的native intersect/transform/round；保留float32路径、bbox origin、150/72与scale矩阵相乘次序。≤1280返回dpi150，>1280返回旧matrix且dpi=None；实际PNG保留该分支默认96dpi。 |
| No first allocation | **PASS，限定planner。** 实际函数只做固定尺寸Rect/Matrix/native bbox运算；不接受PDFbytes/handles、不open/get_displaylist/get_pixmap。测试在planner执行期间禁止open、Page/DisplayList render和native pixmap allocation；静态审阅无IO/codec/launch调用。测试设置和旧oracle渲染在guard外明确执行。 |
| Error / dependency | **PASS。** invalid/empty/engine_unsupported固定local ValueError；未知版本/缺symbol/不可导入引擎fail closed，PNG不依赖PyMuPDF。测试覆盖native错误信息清洗、非有限结果及非法bbox。没有新增依赖。 |
| File import versus package import | **PASS file-only；普通package purity未成立。** 见下方实际negative probe。现有initializer不在两文件租约内，后续integration须单独处理。 |
| Source permissions / shared audience / native lifecycle | **NOT APPLICABLE to arithmetic acceptance；消费边界未验。** 无授权对象或来源读取，不能据此关闭A1负向oracle、#42 ABI或#43原owner gates。 |
| Linux / resources / full product | **PENDING / not accepted。** 本轮无Linux执行、kernel limits/IPC/retained-output测量、production activation或UI验收。 |

### Independent required-suite execution

Interpreter: `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -`，实际打印 **Windows-11-10.0.26200-SP0 / Python3.12.14 / PyMuPDF1.28.2 / Pillow12.3.0**。此为本次独立环境，未改写developer证据所记录的Python3.12.10环境。

PowerShell进程环境设`PYTHONDONTWRITEBYTECODE=1`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`；inline runner以以下参数调用`pytest.main`：

```text
--noconftest --strict-markers -p no:cacheprovider
-o pythonpath= -o xfail_strict=true -q
apps/api/tests/test_native_image_geometry.py
```

Runner在collection前安装MetaPathFinder拒绝`ai_pdf_api`、`ai_pdf_worker`、`citeframe_contracts`所有导入；拒绝socket/socketpair/create_connection以及getaddrinfo/gethostbyname/gethostbyname_ex/gethostbyaddr。Guard插件记录全部collection、deselection和test reports，要求collected==passed call reports==119、exit0、无skipped/wasxfail/deselection；结束断言实际`geometry_under_test.__file__`为本worktree候选路径且上述应用包未载入。没有conftest、自动插件、pytest cache或bytecode写入。

**Actual output: `119 passed in 1.50s`; `REVIEW_GUARD 119 119 []`。** 没有missing-engine skip或选择性排除。

检查并实跑的语义证据：
- **48 PDF matrix cases**：300×400/A4/Letter × 4 rotations × ordinary/offset cropbox × full/fractional region；旧函数AST来自实际hash-pinned原文件。每例比较PNG原始bytes、first/final bbox、DPI及metadata。该测试矩阵fractional值/offset与前轮实验不完全相同，各自按同输入old/new比较，不混用历史fixture digest。
- **10 complex PDF cases**：无/有annotation（保留旧default annotations=True）、透明图元、small embedded RGBA、负/正media origin、直接/继承位置UserUnit、rounding两侧。合计58条PDF属性记录，其中8例matrix/96dpi。UserUnit与复杂fixture证明这些具体字节输入在当前引擎上的旧/新一致，不外推为所有PDF语义已穷尽。
- **64 tiny PNG各两组**：RGB64张、4416bytes、ordered SHA `3f31e1d2e47899f6483d9578c5890513f32750203c77b8c775a9a21531a2c26d`；RGBA64张、4480bytes、SHA `96abbf8bfd23e714bbe85454db90cc8cec280fccf217c2cb2ae572d946bb71a0`。每张1×1，逐byte和顺序与旧函数一致。未把早期不同fixture的5120bytes当作当前expected。此处验证64 arithmetic outputs，optional4组装和整体admission仍不在实现中。
- malformed/strictnumeric/empty/disjoint/unsafe intermediate、冻结返回对象、Decimal ambient变化、unknown/missing engine、无生产caller扫描及file-location import negative均实际通过。

### Independent reverse probes beyond the submitted119

同一只读解释器、禁用bytecode，inline脚本在内存构造全部fixture；再次拒绝应用包与socket/DNS，无真实网络/模型/存储调用。

1. **96个额外真实PDF old/new对照，全部通过，其中10个downscale。** 页尺寸为(300,400)、(595,842)、(612,792)、(614.399,300)、(614.4,300)、(614.401,300)，分别×4 rotations×2 cropbox（原box或15/20/−25/−30 offset）×2 region（full或.0137/.0273/.7319/.6187）。独立小fixture绘制彩色矩形和`Independent R5 geometry`文字；从原文件AST提取旧crop函数及150/1280常量，未调用提交测试的make_pdf/assert_pdf_parity。逐例比较实际old PNG与候选final-only输出bytes、first/final bbox、150/96dpi。另一个fixture-only first render用来验证first_bbox，没有进入候选planner。
2. **1280分支反向门槛实际证据**：无offset、rotation0、full region时，614.399与614.4pt得到first/final `(0,0,1280,625)`、dpi150；614.401pt得到first `(0,0,1281,625)`、final `(0,0,1280,625)`、dpi=None且实际96dpi。未发生用extra ceil改变分支或混用150dpi的差异。
3. **512个独立PNG算术对照全部通过**：固定`random.Random(44012)`，x/y<.8，extent按剩余归一范围生成，维度分别从1/32/127/2^31−1及1/33/257/2^31−1选取；expected直接执行原`_pixel_floor/_pixel_ceil` under default Context。candidate在ambient precision1、ROUND_UP、Emin−1/Emax1及所有Decimal traps开启时运行，结果相等，外层context flags/traps/precision保持不变。
4. **14个额外strict rejection通过**：tuple subclass、Decimal leaf、int/float subclass、会在coercion/comparison时抛AssertionError的对象、10^1000整数、NaN各自送入PNG和PDF路径，均为精确`native_image_geometry_invalid`，没有触发自定义coercion或native成功路径。
5. **实际oracle fixture的drift反例通过**：仅在内存patch `Path.read_bytes`，分别向两个旧source追加synthetic comment；直接调用提交测试`old_oracles.__wrapped__`均报`old oracle source changed`。没有修改原oracle或放松hash断言。
6. **普通包导入negative已实际确认**：允许root/modalities/new module，拒绝其他API子模块；`importlib.import_module('ai_pdf_api.modalities.native_image_geometry')`在既有initializer尝试`ai_pdf_api.modalities.registry`时被阻止。file-location实际源码导入与PNG运行可在所有应用包/PyMuPDF/Pillow禁止时通过；这两个结果分别记录，**没有将file-location加载宣传成常规包纯导入**。后续child/composition入口需在自身租约中明确；本slice不修改initializer或创造临时wrapper。

### Exact old-oracle EOL evidence

独立从当前CRLF bytes计算LF-only和重新CRLF化的SHA，集合与提交测试的两值allowlist完全相等；测试本身对raw bytes取hash，不任意normalize后接受。

| Source | Current CRLF SHA-256 | Exact LF-only SHA-256 |
|---|---|---|
| image_evidence_targets.py | `80A1915CE56EA42CDFB1963724BD5918017274686E8942AC55CCFAE127A26EF7` | `6E4D4F41B3A9EF5201A8390CDCA9C17AC36FE2E37D5E6A074ADF753035FB6DD8` |
| pdf_evidence_targets.py | `9EC66A868D963FAD94ECD594F07D418C5A501B785CEFE7E63DB35351453D3229` | `A520DA2A374FE5289DDE6A109558E068C78908557F030C32278ED8759426398A` |

两个实际fixture drift negative证明内容变化会失败。这里仅验证EOL allowlist准确，**没有在Linux运行测试**。

### Final bounded handoff / remaining gates

**Exact candidate ACCEPT for unactivated geometry code and tests on the observed Windows build。无需原developer为本两文件返工。** 当前结构保持小型数值算法职责，能够支持后续受限child中的旧final-transform一次渲染路线；无产品caller使它保持未激活状态，没有引入空壳runtime。

- NI4中“当前Windows numeric/fixture implementation”得到本次证据；**full legacy parity/NI4整体不关闭**。Linux pinned PyMuPDF/Pillow重跑byte/bbox/DPI和复杂输入矩阵仍必需，未来CI collection由controller另行安排。本轮没有CI权限或hosted运行结论。
- NI1 retained outputs/base64/archive全生命周期、NI2 startup/credential/env/FD/core/parent-death、NI3可取消bounded IPC仍待批准实现和真实Linux测量；**native launcher/build仍未获授权**。planner不构建display list；未来caller的PDF parse/display-list成本仍必须进入实际硬资源边界。
- NI5 source identity/geometry结果、source authority/entire audience、#42 exact shared image ABI、#43 lifecycle及loader/dispatcher integration仍归原owners。本轮不增加对应文件、接口或owner；不授予runtime/native activation。
- 不批准生产capacity、候选资源常数或exact image token counter；不宣称同run循环/压缩、旧mode1/mode2 SSE或实际UI已验收。既有provider/profile/builder closures全部保留。

只追加本review；产品/tests/CI/依赖/合同/其他review均只读，无Git writes、commit/push、paid/live模型、服务/DB/网络/UI操作。已有chat-loop修改保持不动。Durable write-back即本原review，无private memory或shared-workbench写入。Controller负责提交和后续授权。


## Independent targeted geometry CI review — 2026-09-29

**Disposition: ACCEPT — exact dedicated workflow and evidence-attribution delta, eligible for controller commit/push. No blocking CI finding. Hosted Linux execution remains PENDING.** 原geometry代码ACCEPT（本review追加前SHA `FFBEDACA637148142EA518154ABA6AC31BAE77B560FD705CBB9C1F35ABA4BDF9`）保持，不重开已关闭算法项。

### Exact reviewed manifest and governing scope

工作树/HEAD仍为`D:/Code/citeframe-lanes/issue44-provider` / `7d6be8a236d48135460b0a5677b6ea01edd31b4f`。审前核对以下原始bytes，交付前再次确认不变：

| File | SHA-256 |
|---|---|
| .github/workflows/memory-image-geometry.yml | `82600A9CCA24A89F1FBC70460E9F0F9CBE23A4E1D370FD9AE86B01F16F4C5D26` |
| specs/v5/memory-management/evidence/issue44-native-image-geometry-ci.md | `718B7223EC28B764B8FA3EC3B587B4F902FD0217300D61185E5C624410DEE093` |
| specs/v5/memory-management/evidence/issue44-native-image-geometry.md | `5847DE5FB1282D5F4897E714343DE7ADF20D27F3DFB0B5317C7DC8243979C872` |
| apps/api/src/ai_pdf_api/modalities/native_image_geometry.py | `62B89093C67B88B16CB926C61A4DC1FC3725341332350B32BD88FFCA4532368C` |
| apps/api/tests/test_native_image_geometry.py | `538AB2C3575E04EDC66BBC2DBC43A573DE05BCB9B07B3598CCADB902FA3B25F2` |

本CI的直接目标是在独立Linux job运行已审真实old/new geometry oracle，强制119实际call成功并拒绝虚假绿灯。v4/A1选2的共享上下文/来源边界、同run压缩和完整native资源目标继续有效；CI自身不实现或验收这些消费路径。没有将test count或job配置视为Linux parity已经完成。

### Workflow review

| Item | Judgment |
|---|---|
| Trigger / job scope | **PASS。** PR及main push均覆盖new source/test、两份actual old-oracle source、API pyproject/lock、四个local-source包manifest以及workflow本身。独立`native-image-geometry` job，无PG service、DB fixture collection、模型步骤、secrets、schedule或额外权限。仅contents:read、10分钟job timeout。 |
| Frozen environment | **PASS configuration。** setup-python及UV_PYTHON固定3.12系列，body断言实际major/minor为3.12；未固定patch版，不声称字节级固定解释器。`uv sync --project apps/api --frozen --extra dev`，随后`uv run --project apps/api --frozen --no-sync python`；没有lock/dependency改写步骤。 |
| Dependencies / Linux executability | **PASS static prerequisite check；install/runtime待hosted。** 实际API lock含PyMuPDF1.28.2、Pillow12.3.0、pytest9.1.1；存在x86_64 manylinux cp310-abi3 PyMuPDF、cp312 Pillow和pytest通用wheel。四个editable local-source路径及manifest在当前树实际存在。未运行uv sync，未借Windows环境声称Linux安装成功。 |
| Exact selection | **PASS。** 唯一显式path为`apps/api/tests/test_native_image_geometry.py`；missing path先失败，--noconftest、strict markers、no cache、pythonpath override及xfail_strict均保留。无-k/-m过滤、ignore/importorskip或continue-on-error。运行后核验实际geometry module文件路径。 |
| Execution / outcome gates | **PASS。** collection及call成功数均须119；collection/runtime skip、wasxfail（含nonstrict XPASS）、deselection全部拒绝。collect-only无call不会绿灯。正常pytest非零status不被成功计数覆盖，最后按status退出。下述独立控制实际验证。 |
| Import / network guard | **PASS bounded test guard。** 在pytest import前安装API/Worker/contracts MetaPathFinder以及socket/socketpair/create_connection和五个DNS入口denial；结束断言应用包未载入。没有执行应用settings/DB。此为测试进程Python入口guard，非Linux内核网络sandbox；file-location import限制按原review保留。 |
| Existing lanes / privilege | **PASS。** 对既有workflow、API manifest/lock及packages的read-only diff无本delta改动；没有放宽共享CI或原neutral/profile/builder选择。权限没有升级，无pull_request_target或secret使用。 |
| Actual Linux parity / hosted result | **PENDING。** workflow将运行原119真实Pillow/PyMuPDF oracle与精确CRLF/LF hash检查，缺版本/依赖须失败；本轮尚未执行Actions。 |

### Independently executed exact syntax and positive runner

1. **actionlint实际执行通过**：

```text
D:/AI/tmp/actionlint-1.7.12-windows-amd64-20260905/actionlint.exe -version
D:/AI/tmp/actionlint-1.7.12-windows-amd64-20260905/actionlint.exe -no-color .github/workflows/memory-image-geometry.yml
```

版本输出1.7.12；workflow检查exit0、无diagnostic。没有下载、安装或拒绝后的绕过。Candidate CI evidence中`Actionlint: BLOCKED / NOT RUN`记录其原developer当时的工具条件；此处记录原appointed reviewer对相同workflow hash的后续实际通过，不借用controller的另一次结果。

2. **实际run scalar的Bash语法通过**：按YAML block缩进去除10空格，将包含uv命令和heredoc terminator的完整scalar送入既有`C:/Program Files/Git/bin/bash.exe -n`，exit0。body另经Python AST parse通过。这是Windows上的Bash syntax验证，不是Linux job执行。

3. **unchanged heredoc实跑通过**：使用`textwrap.dedent(workflow_text.split("python - <<'PY'\n",1)[1].rsplit('          PY',1)[0])`提取body。提取后UTF-8/LF body SHA-256为 **22BADF014A84715E2E22492F3C460AEA3D961DE01A91CAA6C595B5261A776F5C**。不改body，交给`D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -c <body>`，cwd为本worktree。设置workflow两个PYTHON环境变量，清除local PYTEST_ADDOPTS，未执行外层uv命令。

**Actual result: `119 passed in 1.52s`, exit0。** 实际本地环境：Windows-11-10.0.26200-SP0、Python3.12.14、pytest9.1.1、PyMuPDF1.28.2、Pillow12.3.0。这是原reviewer独立运行，与developer、developer-root及controller报告分开。

### Independently executed negative controls

以下只修改内存中的runner副本或注入reviewer-owned plugin，不改workflow/product/test文件；每个whole-runner控制以同一解释器新进程运行。

| Control | Actual observed result |
|---|---|
| required path不存在 | exit1，精确missing-file错误 |
| 增加--collect-only | 收集119但零call，exit1 |
| -k排除一个已有test | 118 passed / 1 deselected，exit1 |
| 首个test runtime skip | 118 passed / 1 skipped，exit1 |
| call hook触发pytest.xfail | 118 passed / 1 xfailed，exit1 |
| 首个test标记nonstrict xfail且实际通过 | 118 passed / 1 xpassed，exit1 |
| call hook抛真实AssertionError | 1 failed / 118 passed，exit1 |
| 最后一个test在正常teardown之后抛错误 | **119 passed / 1 warning / 1 error，exit1**，验证成功call数不能遮蔽teardown失败 |
| 将Python版本assert的expected设为不匹配值 | 在测试前AssertionError、exit1 |

Teardown probe的第一次注入发生于首个item清理前，实际得到118 passed / 2 errors和非零退出；reviewer自身外层预期单个error的断言失败。随后将自有probe精确改为最后item正常teardown后的hookwrapper，得到表中119 passed / 1 error。这是probe调整，没有候选workflow修复或产品故障。

另直接AST提取**实际workflow中的RequireExecutedTests原class**作report/session级控制：healthy119/119返回0；collection-skip、runtime-skip、deselection、wasxfail即使配119/119也返回1；collected118/120或passed118/120均返回1；原status1在119/119时保持1。此为guard unit控制，与上表真实pytest运行分开记载。

实际执行workflow的guard前缀后，尝试导入API、Worker、contracts，三个入口均抛其指定denial。socket/socketpair/create_connection/getaddrinfo/gethostbyname/gethostbyname_ex/gethostbyaddr/getnameinfo共8个调用全部在denial函数处拒绝，没有创建真实socket或DNS请求。这些控制验证当前runner入口确实装上guard，不将其当作抵御任意恶意native code的安全沙箱。

### Evidence attribution and final handoff

**证据归属修订ACCEPT。** SHA5847…将先前119/2.41s及guard明确改归developer-root；原119/2.37s归implementation agent；controller119/1.45s按其报告独立记录，不替其附加其他执行者的guard；原reviewer119/1.50s及96PDF/512Decimal/14strict probes归属保持。新CI evidence把两个119/2.19s分别列作implementation agent与developer-root，明确均非appointed independent reviewer。本节119/1.52s及negative controls才是此次独审实跑。前文保留的原始evidence actor叙述是当时引用记录，最新归属以本节和SHA5847…为准。

**CI文件可冻结提交；不需要原developer修改这个候选。** Controller commit/push后必须另记录实际hosted Linux run及结果，才能关闭该平台的parity执行门槛。workflow建立真实旧函数矩阵的执行入口；未声称任何未发生的Linux PASS。

本轮只追加原review并保留全部历史字节。未改产品/tests/CI/evidence/依赖或Git；没有uv安装/实际网络/模型调用。原geometry ACCEPT与所有provider/profile/builder closures继续有效。NI1–NI5未关闭的resource/source/integration gates、#42/#43原owner边界仍保留；**launcher/build未授权，native activation和UI未验**。Durable write-back为本artifact，无private-memory/shared-workbench写入。
