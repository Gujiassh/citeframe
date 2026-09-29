# GenerationImage 最小共享 ABI — 独立 Critical 合同审查

日期：2026-09-29。  
**当前结论：ACCEPT §7 精确第一阶段实现：独立 GenerationImage、有界结构 validator、export 和 59 项 contract tests。GI01 的该实现范围关闭。GenerationMessage 仍四字段；消费者、native admission、CI/image runtime activation 未接受。设计批准见 §6。**

以下 §§1–5 保留首次候选 e57f9487 的原始审查和证据；§6 保留精确设计批准；§7 为当前第一阶段实施结论。

候选：`specs/v5/memory-management/lanes/issue42-generation-image.md`  
精确 SHA-256：`e57f9487c6310cf4cde2e62254997a51b1d8ebd0d2fa862010a2224d414698b2`。

## 1. 目标与证据范围

目标是已授权 native PNG 输入的最小共享值类型：保留原始 PNG bytes、文本在首位及图像顺序/detail，保持旧 text-only 调用与规范序列化/hash 合同，并由原 owner 继续负责实际来源与资源 admission。无新 private audience、source registry、通用 content-part union、模型能力默认值或原文删除语义。

本轮为合同审查。只读核对了实际 shared memory DTO、native chat builder/两类映射、#43 request/tool archive 消费点和已接受 history request hashing；没有实现 ABI、修改 adapters/history/#43 文件、调用模型或运行 image pipeline。以下标准库探针说明分配与兼容风险，不能作为候选实现/runtime acceptance。

## 2. GI01 — 构造校验必须在全量 base64 转换前有独立硬边界

**P1；目标：候选 32–34、58–60、64、67 行。**

候选要求 canonical `decode→encode` 等值，并将尺寸/数量/字节限制放在后续 #44 profile、#43 archive 和 native admission。§5 正确说明 DTO 不能补救上游读取/解码过量，但尚未给 **DTO 自身** 的长度/分配/工作量界限。

`GenerationImage(...)` 的构造先于消费者 profile 校验。一个已经存在的任意长 `data_base64: str` 即使最终被 profile 拒绝，结构校验仍可能先进行全串 ASCII copy、base64 decode、再次 encode 和字符串转换。只检查 PNG width/height 不限制 metadata、尾随数据或编码串长度；只禁止 Pillow/I/O 也不限制这些 Python 分配。声明 native 输入“已获准”不能替代此边界，特别是直接构造和 archive restore 的独立入口。

### 必须补齐的有限合同

1. **明确命名、具体数值的 ABI 结构硬上限**：至少每图 encoded-character/decoded-byte ceiling；新增 images tuple 的结构数量上限也须在遍历前检查。说明常量/版本由 #42 唯一 owner 持有。它们是验证器可处理的最外层结构范围，不能当作任意模型的能力、生产 profile 默认值或 native 安全证明。profile/native/task 限制可更小且仍独立强制。不要留下“稍后由 profile 检查”的空白。
2. **规定检查顺序与自身资源界限**：先 exact scalar/tuple types 和 O(1) `len` 拒绝，再处理字符/padding。在 ASCII encode、完整 decode/re-encode、全串正则/复制/hash 之前执行长度门；按 padding 精确求 decoded length 并在分配前检查。若 decoded cap 为 B，encoded ceiling 的关系 `4 * ceil(B/3)` 不能代替最终 decoded-length 检查。canonical roundtrip 可在已界定范围内执行，或用有界等价算法；不能因改用流式扫描而省略总工作量上限。
3. **明确 PNG 结构检查的有限范围**：固定 header 的长度、signature、首个 IHDR 的 type/length/完整尺寸字段及字段等值；不读取声明的巨大 chunk length 来分配缓冲，不遍历/解压图像。最小完整 IHDR、尺寸整数范围及是否校验 header CRC 应在实现合同/测试中明确，避免把 signature+若干字节等同于完整 PNG 验证。无需扩成 Pillow/full PNG decoder。
4. **保留诚实边界**：传入 str、原始对象下载、JSON parse、native decode/render/PNG encode 的先前分配不受 DTO 追溯保护；§5 admission 仍必须由 native owner 先完成。新增结构上限不能用于宣称这些上游路径已经安全，也不能通过缩图/重编码/少图使输入通过。
5. **必要验证**：exact cap 正例/一单位超限反例、padding 导致 decoded 长度越界、非 ASCII、非 canonical pad bits、截断/伪造 IHDR、tuple 数量边界。超限路径用 spy 证明没有调用完整 base64 decode/encode 或后续 counter/profile/provider，不必制造真实巨量输入。记录有限正常输入下的验证器峰值分配及有界循环/复制次数；格式化错误/traceback 不泄漏 payload。结构错误仍使用既定 `ProtocolError("generation_input_unsupported")`。

要求针对新构造验证器本身，不要求本轮实现上游 decoder worker、全量 native 安全改造或生产模型容量。GI01 修订后仅复审精确 bound、检查顺序和对应定义/tests 范围。

### 独立有界探针

在本树以 `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -` 执行标准库探针。预先生成 canonical ASCII 输入后才启动 tracemalloc；仅测 `base64.b64decode(value, validate=True)` 加 `base64.b64encode(raw).decode('ascii') == value`，无像素解码、provider 或候选实现调用。最大 decoded 输入仅 1 MiB：

| decoded bytes | input characters | peak additional tracked bytes | canonical 等值 |
|---:|---:|---:|---|
| 65,536 | 87,384 | 240,411 | true |
| 262,144 | 349,528 | 961,307 | true |
| 1,048,576 | 1,398,104 | 3,844,891 | true |

这证实普通严格 roundtrip 的额外内存随输入增长；不是候选实现基准，也不证明精确进程 RSS/完整 decoder 上界。没有预先长度门时，合同允许的验证器额外分配没有确定最大值。因而不能用“最终 profile 会拒绝”关闭 GI01。

## 3. 其余合同判定与必要实施读法

| 项目 | 判定 |
|---|---|
| 单一 DTO / 不可变字段 | **pass at design scope**。唯一 #42 GenerationImage；字符串承载避免两份可分歧 bytes/base64；images 为 tuple、成员严格类型。无新 ports/source identity 或循环导入。 |
| canonical bytes / PNG 含义 | **原则 pass；资源边界由 GI01 补齐**。标准 alphabet、严格 padding、无空白、canonical 等值和原字节保留正确。PNG metadata 不得被静默删除或重编码；结构通过不证明 IDAT/CRC/完整文件可解码。后者仍须 native admission。 |
| role / native 顺序 | **pass at design scope**。仅无 tool_calls/tool_call_id 的 user message 可有 images；text str 在前，原 tuple 顺序在后。禁止 system/assistant/tool 图像、交错 parts 和工具图像结果。原生 builder 先 targets.image_payloads 再 extra_image_payloads，detail=high，与候选一致。 |
| repr / errors | **pass at design scope，需实现 oracle**。`data_base64` repr=False；嵌套 GenerationMessage/GenerationRequest repr 也不能显示图像 payload。结构错误需稳定 code，不拼接输入、不泄漏 chained codec/parser exception。`asdict`、正式 archive/wire 序列化仍包含原图，repr=False 不提供其脱敏保证；不得把这些对象直接作为诊断日志。 |
| source 权威在外 | **pass at design scope**。DTO 不携带可构造 source_ref 权限；原 owner manifest 以 message/image ordinal 绑定真实对象/version、locator/region、转换参数、最终 PNG hash 和全部真实依赖。crop hash 与原 source hash 不混用。缺真实 seam 时拒绝激活；读取、restore、dispatch/adoption 均重验当前权限与失效状态。实际 manifest delta 尚未接受。 |
| 三协议 serializer/counter | **pass as gated handoff**。Responses/ChatCompletions high 与 Anthropic 无 detail 的表述和实际 native mapping 一致。支持能力/profile/真实 image accounting 尚未实现或接受；base64 长度不当 image tokens。估算/exact 证据分离、零网络拒绝保留。 |
| summary / packing | **pass as gated handoff**。图像整单元和来源保留，当前问题受保护；text-only summary 不能只取 content 丢图或产生无来源替代文本。装不下明确失败，不裁剪原图、不自动 OCR。未授权修改 #43 当前施工。 |
| 旧四参数构造 | **pass at design scope**。新增 field 位于四个旧字段之后，默认 ()，保留正常旧 positional 调用。此项与序列化/hash 兼容必须分别验证。 |
| text asdict/hash 与消费版本 | **pass as explicit integration gate**。候选已经明确裸 asdict 会变、old text 写出省略 images、旧 reader 缺字段得到 ()、不改历史 digest；image-bearing 使用正式新 version，unknown version/fields 拒绝且 restore 不静默丢图。具体编码/projection/manifest 版本 delta 仍须各原 owner 提交独审。不得以本轮设计批准替代该审批。 |

### 实际 text-only 兼容风险已核实

当前共享 `GenerationMessage` 正好四个 dataclass fields，无 images。实际消费点：

- #43 `compaction/requests.py`：`canonical(asdict(request))` 写出及 `digest(asdict(request))` 比对。
- #43 `compaction/archive.py`：`asdict(m)` 写 tool-group 原文；reader 明确调用四参数 `GenerationMessage(...)`，不消费新增 image 字段。
- 已接受 #42 `history/ranges.py::request_hash`：直接 canonical `asdict(request)`。

独立标准库探针用真实旧 DTO 构造 `GenerationRequest((GenerationMessage('user','hello',(),None),),128)`，按现有 sort_keys/UTF-8/紧凑 JSON 计算 SHA，再仅对 asdict 结果每个 message 加 `images=()` 模拟 additive dataclass 字段的输出：

- 原 text request：`6a4c0a68b219e50238694606c3408d5e82b12ac1311e00bcd9816342216b5c21`
- 加空 images 后：`dfdb68a25f6332a19b4c97d77f0befd16951a234da2781bf614d33aab7e86673`

因此**关闭 image activation 不能单独保持 text hash**。这是候选 §4 已识别风险的实际验证，不另发一个重复设计 finding。正确阶段边界是：定义 GenerationImage 可先行；把 images 追加到被共同加载的 GenerationMessage 前，必须完成并批准所有实际消费者的兼容投影/reader 版本同步。不能先合入 additive field，再以“只允许空 tuple”为兼容措施。冻结 history 仅经其 owner 的单独 narrow grant 修改，不因本 review 自动解冻。

## 4. 最小非重叠实施阶段

**本精确版本由于 GI01 尚不能批准构造校验实现。以下分阶段结构接受；原开发补齐 GI01 后可据精确修订授权。**

1. **#42 定义/tests 阶段**：`packages/backend-contracts/src/citeframe_contracts/memory.py` 中单一 GenerationImage 及明确 bounded validator，`citeframe_contracts/__init__.py` export 和 controller 指定的专有 contract test 文件。无 serializer、registry 或 native loader。可先定义/测试 GenerationImage；此阶段不向在用 GenerationMessage 追加 images，不改变现有 text asdict。
2. **正式消费者 delta 阶段**：#44 提交 serializer/counter profile 的有限能力/limits/accounting 变更；#43 提交 request encoding、reader/restore、source/crop manifest、packing/summary 的实际新版本和 legacy projection；#42 history hashing 另给 narrow owner grant。各自精确审查后由 controller 串行安排 additive message field 与所有 consumer 同步。不得指定当前 #43 I3/I4 实现为已接受基线。
3. **关闭状态下的集成证明**：旧四参数与 text wire/canonical/hash fixtures、旧 archive reader、未知版本/字段拒绝、image restart 原字节/ordinal/ref 相等、counter/framing 全量计数及零发送拒绝。新版本不得在混合 reader 部署中被旧四参数恢复器静默降级。
4. **真实 image activation**：native read/decode/render admission 与 aggregate/preallocation 证据、真实 source 权威及权限/删除 suppression 通过后，才可启用正常 text+image 回答和重启链路。需要实际 native fixture parity；本合同/拒绝用例/标准库探针均不接受图像实际可用性。

#42 唯一 shared DTO owner、#44 serializer/counter owner、#43 archive/packing owner 的分工保留。不转交源 registry，不新增私有受众或随意扩大文件所有权。

## 5. 只读证据身份与交付

| 实际文件 | SHA-256 |
|---|---|
| 本树 packages/backend-contracts/src/citeframe_contracts/memory.py | b1a0d53b5d21bac31ac12609a5a798cceda5f9aab43eeffaa4e178a3d9d5aae45 |
| 本树 apps/api/src/ai_pdf_api/services/chat.py | dd6d28f8629c1655aca238b817ace9be81c4dfb33c4198027b8fe9f966973c91 |
| 本树 apps/api/src/ai_pdf_api/services/chat_completions.py | 1de65a326e5f0b7555e0f5251524acb04b92f82d0d1eedeb01aed5d66e9258dee |
| 本树 apps/api/src/ai_pdf_api/services/providers.py | 8338579b25493c2ae1d837fcccd675f8f80b169c7ec22cf04fc9082aa755501e |
| #43 compaction/requests.py | 7fb058c9b566fd025b2762012eddc47772bb48e442835c3b65416659a2ba9477 |
| #43 compaction/archive.py | 87bd63c47a8d3a9ebcd8b214f3004cc5ffe8ba4b040bcde2a957487e42d2d5e6 |
| #44 lanes/issue44-chat-loop.md | 339a377a52e78d87d20710878638db720501b847a3df3d14349a69e6656138e5 |

#44 文档已较候选引用 hash 前进；本轮读其实际 §§16/19/21 与 native 代码，仅核对 ABI 提案和 admission 边界，不接受其移动实现。

仅新增此 review。候选 hash 写入前重新核对；原 `reviews/issue42-shared-sources.md` 保持 `f14a8a77992665580f9bdd4b07045ac4601892d03cc39251d92865d962f952ec` 未修改，其已接受 pure-history/P1a 范围不变。无产品/tests/ABI/CI/Git、#43 施工、全局/private memory 或 canonical #40 写入，无数据库/模型/付费调用。durable write-back 限于此评审文件。


## 6. GI01 精确修订复审 — 2026-09-29

**APPROVE 第一阶段设计并允许原 #42 开发按 controller grant 实施；GI01 design CLOSED。没有新增具体设计缺陷或剩余设计阻断项。**

实际复审候选：`specs/v5/memory-management/lanes/issue42-generation-image.md`  
SHA-256：`8f6870b96deb4815161a3fd37676aadc0f11bcfe263213d2ed336d662712e313`。

本轮只核对原 GI01 修复与 text asdict 同步顺序，不重复其余已认可的设计。controller 已明确裁决以下数值为待实现验证器的工程结构上限；本结论不把它们解释为生产模型容量或 native 图像产品限额。

### 6.1 GI01 闭合依据

| 原缺口 | 修订实物与结论 |
|---|---|
| 构造前缺确定长度/工作量上限 | **pass，38–52 行。** `generation-image-structure-v1`、B=4,194,304 decoded bytes、E=5,592,408 encoded chars、PNG dimension≤2,147,483,647 明确；先 exact types / O(1) len / n%4 / 固定范围，再至多两字符推导 padding 和 D，最后才扫描与转换。caller/profile 不可覆写这些结构常量。 |
| 只限制 E 仍能解码超过 B | **pass，51 行。** D=3*(n//4)-p 在完整 ASCII/base64 转换前检查。E 长度对应 padding=0/1/2 时，D 分别为 4,194,306 / 4,194,305 / 4,194,304；前两者先行拒绝。独立算术探针已验证这些精确值及 E=4*ceil(B/3)。 |
| 转换多份全长分配无界 | **pass at design scope，52–54 行。** 一次有界字符扫描、一次 ASCII encode、一次 strict decode、一次 encode，bytes 等值而不再生成全长 roundtrip str；无重试/递归/hash/全串 regex。局部大缓冲界限明确，输入预构造后的额外 tracemalloc peak≤32 MiB 是实现交付门，尚未执行/接受候选 validator 峰值。 |
| PNG 结构检查范围未定 | **pass，53 行。** 只访问固定33-byte signature+IHDR，要求 length=13/type、CRC32 的17-byte输入、标准 bit-depth/color-type、compression/filter/interlace 和尺寸等值。不会依任意 chunk length 分配或遍历/解压后续数据。33-byte IHDR-only 可通过结构层的限制写明，完整 IDAT/IEND/后续 CRC/尾随内容有效性不由本 DTO 证明。 |
| 新增 tuple 遍历缺界 | **pass for the future second-stage design，46、50 行。** 先 exact tuple 和 len≤8 再遍历，超限不复制或重验成员。这个验证尚不实施于现有 GenerationMessage；8/9 tests 也归第二阶段。上限8不授权 native 少图、裁剪、缩图或改变产品输入语义。 |
| 隐私与上游边界不明确 | **pass，54–56、86 行。** 稳定 ProtocolError、codec exception `from None`、无 payload/locals 日志、嵌套 repr 不显示图片；既有 str/JSON/download/encode/decode/render 分配不可追溯保护。后续 profile/native/task 必须独立执行更严及 aggregate admission，未审 native bounds 仍不接受。 |
| 缺验证器自身证据门 | **pass as required future tests，58 行。** 真正常量 B/E 边界、B+1/B+2 推导 D、E+1、padding/non-ASCII/pad bits、IHDR/CRC/尺寸、转换计数及 spy 零转换/零外部调用、峰值和隐私测试都被明确列出。小整数 helper 测试不能替代真实 B/E 用例。 |

标准库算术检查另确认最短33 bytes canonical base64 为44 chars。没有为本轮重新生成大输入，也没有编写/执行候选 validator；审批对象为上述精确规则和测试要求。

### 6.2 旧 text asdict/hash 顺序确认

修订 28、97–99 行明确区分两个阶段：

1. 先只新增独立 GenerationImage/value validator/export/tests；**现用 GenerationMessage 保持四字段**。
2. #44 serializer/counter、#43 legacy projection/request encoding/archive restore/source manifest/packing、#42 history hashing 的正式 version delta 分别先审，随后 controller 串行同步消费者和 additive message field。
3. 消费版本回归后仍需 native admission、真实来源权限和 parity，不能以 activation=false 或 images=() 冒充 text digest 兼容。

该顺序覆盖首次 review 中实测的 asdict 风险。此轮重新读取实际共享 memory.py：hash 仍为 `b1a0d53b5d21bac31ac12609a5a798cceda5f9aab43eeffaa4e178a3d9d5aae45`；独立进程检查 GenerationMessage 的 dataclass fields 仍精确为 role/content/tool_calls/tool_call_id。原四参数 text fixture 的 canonical request SHA 仍为：

`6a4c0a68b219e50238694606c3408d5e82b12ac1311e00bcd9816342216b5c21`。

这是当前未改基线的复核，不能替代未来实现后的兼容测试。

### 6.3 本次唯一实施 go-ahead

原 #42 开发可在 controller 明确文件 grant 内实现：

- `packages/backend-contracts/src/citeframe_contracts/memory.py`：单一独立 GenerationImage、上述结构版本/常量及有界 validator；不更改现有 message/request 类型及其行为。
- `packages/backend-contracts/src/citeframe_contracts/__init__.py`：该单一类型所需的最小 export。
- controller 指定的一个新增专有 contract test 文件：第一阶段结构/隐私/不可变性/资源峰值与 spy 边界证据，并保留旧四参/text asdict/hash 基线。

**不在本次授权范围：** GenerationMessage.images 字段或 role-image 校验、message tuple8/9 行为的正式接入、任何 #44 serializer/counter/profile、#43 archive/packing/施工文件、history hashing、source manifest/registry、native loader、schema/migration/CI、实际 image/runtime activation。可声明未来结构常量，不得由当前 native 产品使用它静默减少图像。

实现完成后对精确代码、真实边界/peak/spy 与兼容 tests 作实施复审；设计批准不预先接受这些结果。没有等待完整 #43 或重开整个 image 设计的要求。

### 6.4 证据与写回范围

本轮仅更新本原 review，保留首次发现与探针历史。候选 hash 写入前再次核对。原 `reviews/issue42-shared-sources.md` 仍为 `f14a8a77992665580f9bdd4b07045ac4601892d03cc39251d92865d962f952ec`，未改动；已有 pure-history、P1a/admission 接受范围均不变。无 ABI/产品/tests/consumer/Git/#43 施工/共享私有记忆写入，无数据库/模型/paid 调用。durable write-back 限于本评审。


## 7. 第一阶段精确实现独立审查 — 2026-09-29

**ACCEPT 以下冻结候选。未发现本轮第一阶段范围内的阻断问题。**

接受目标：可独立构造的 bounded PNG structure value、单一 export、实际资源/错误/不可变性边界与原 text contract 兼容；设计为已批准 `8f6870b9…`。不把结构 DTO 扩展为 native PNG 完整有效性、来源授权、视觉能力或已激活消费者。原 history/P1a/admission 结论不变。

### 7.1 精确身份

| 文件 | SHA-256 |
|---|---|
| packages/backend-contracts/src/citeframe_contracts/memory.py | f168652de5a5c103fe177f20f6f747b2db966218772fe650f9e38771b004163d |
| packages/backend-contracts/src/citeframe_contracts/__init__.py | 90096c370eec9ab6452562b844dc0b5a55ce0435138fe6660f8efcfa4f828e25 |
| packages/memory-service/tests/test_generation_image_contract.py | 49e806b7681b76e8dac43ac02e27356dab62551a7909766ff8af4fd7f049003f |
| specs/v5/memory-management/evidence/issue42-generation-image.md | 86bf580d77def9a7cccf4ac626143bef8dbb38556e5fe0e62260a1010818aff9 |

实际检查了两个产品文件的 Git diff、全部新 validator 和测试、开发者 evidence。写入本节前重新核对四个 hash，未以报告代替代码审查。

### 7.2 代码语义与测试判定

| 项 | 判定与实际证据 |
|---|---|
| 严格类型和最前边界 | **pass**。exact str/int 排除 bool、subclasses 和可变容器；固定 media/detail/尺寸检查后只用 len 与 modulo 检查44≤n≤E，再由最后两字符计算 padding/D。所有新完整扫描/ASCII/base64 转换均在 D≤B 之后。 |
| B+1/B+2/E+1 | **pass**。真实 B+1/B+2 输入都具有 E 字符长度，按 D 先行拒绝；原用例证明三个转换 spy 零调用。额外独立控制还用会抛错的 alphabet membership 对象证明这两个 same-E overflow 连 alphabet 扫描也未进入。E+1 的零扫描/零转换在实际59用例中通过。 |
| canonical 表示 | **pass**。一次有限 alphabet/padding 扫描，strict decode(validate=True)，decoded 长度等值，以及 re-encode bytes 等值；不会 strip 或修复输入。无第二份全长 roundtrip str；canonical 原串保留。非零 pad bits 即使被标准 decoder 宽容解码，也由等值检查拒绝。 |
| 固定 PNG 结构 | **pass**。raw 至少33 bytes；只切固定前33 bytes 检查 signature/length13/IHDR、尺寸、标准 depth/color、compression/filter/interlace，CRC 输入固定17 bytes。无 payload chunk traversal、解压、Pillow/PDF/I/O 或按伪 chunk length 分配。33-byte IHDR-only 与最大结构 dimension 的通过均不证明完整 PNG/像素资源安全。 |
| bounded allocation | **pass for this validator/current test environment**。有界扫描和各一次 ASCII/decode/encode，局部缓冲不缓存到 DTO。独立复跑最大4 MiB fixture 的额外 tracked peak为18,179,245 bytes，低于32 MiB门槛。输入先构造，测量含 spy 调用记录；不等价于 RSS、并发、上游读取或解码界限。 |
| repr/errors/frozen | **pass**。data_base64 repr=False，普通嵌套 repr 不显 payload；正常 frozen 赋值拒绝。结构错误固定 generation_input_unsupported；codec ValueError/binascii.Error 转换使用 from None。标准 formatted traceback 无 codec sentinel；无产品日志入口。asdict/正式序列化并未脱敏，不能据 repr=False 将其当日志安全投影。 |
| 原合同兼容 | **pass**。独立 AST 比对 Git HEAD 与候选全部33个既有顶层 class/function 定义，均保持一致；唯一 root type export 为同一 GenerationImage。GenerationMessage 四字段、四位置参数及真实 text request hash 保持原基线。新常量8没有接入 message 或 native 产品限额。 |
| 依赖/架构 | **pass**。新增依赖仅 base64/binascii/zlib 标准库，无新的 authority、registry、adapter 或 app import。此次测试不需要 sibling #43 policy。__init__ 的产品差异只增加 GenerationImage import。 |

现有 overflow tests 中 profile/counter/provider 是构造后局部哨兵；它们证明异常阻断该局部顺序，**不证明真实消费链已接入**。本轮验收核心证据为实际代码的检查顺序、真实 B/E 输入和转换/扫描 spy，不把这些哨兵提升为 adapter/runtime 证明。

### 7.3 本 reviewer 独立运行的59用例与既有回归

工作目录为本 issue42-persistence 树，执行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -m pytest packages/memory-service/tests/test_generation_image_contract.py packages/memory-service/tests/test_admission.py packages/memory-service/tests/test_instruction_memory.py::test_validation_and_fail_closed packages/memory-service/tests/test_instruction_memory.py::test_neutral_import_without_application_packages -q -s -p no:cacheprovider
```

**实际结果：1664 passed in 9.12s，exit 0，零 skips。** 组成59新 image contract、1603 admission、2 P1a validation/import。与开发者1664结果分开归因；本轮未运行或重新接受 P1a PG/migration。

本人运行输出的峰值：

| decoded bytes | encoded chars | additional tracked peak bytes |
|---:|---:|---:|
| 33 | 44 | 3,828 |
| 34 | 48 | 3,855 |
| 35 | 48 | 3,848 |
| 65,536 | 87,384 | 287,797 |
| 4,194,304 | 5,592,408 | 18,179,245 |

实际4 MiB正例的三个转换 spy 各恰一次。上述 measured peak是测试进程分配证据；不声称 native decoder、进程硬内存隔离、吞吐或视觉可用性。

### 7.4 额外独立反例与旧合同核验

另用 `python -B -` 内存脚本，通过 `runpy.run_path('packages/memory-service/tests/test_generation_image_contract.py')` 取 header/encode fixture，调用真实冻结产品函数；无落盘测试修改。补查：

- 对真正 B+1/B+2、encoded恰E 的输入，同时封锁 alphabet membership、ASCII、decode、encode；仅得到稳定 ProtocolError，无任一受封锁操作。
- data_base64/media_type/detail 使用 str subclass、width/height 使用 int subclass；str subclass 的 __len__ 故意抛错。均在调用任何自定义长度/转换行为前被 exact-type gate 拒绝。
- 对 **256种color × 256种depth** 逐一生成 CRC正确的33-byte IHDR；独立标准组合表预期的15种通过，其余65,521种全部以稳定错误拒绝。该有限矩阵证明 header组合规则，未把 header-only fixture 当完整 PNG。
- 对 decoded34/35 bytes分别遍历双 padding的15种、单 padding的3种所有非零 unused bits；先核对标准 decoder 会解到相同原字节，再确认产品拒绝全部18种非 canonical 编码。
- 分别在 _image_ascii、b64decode、b64encode 注入含测试 payload 的 ValueError/binascii.Error。三个路径均有稳定 code、suppress_context，标准 formatted traceback 不含 payload。
- 通过只读 `git show HEAD:packages/backend-contracts/src/citeframe_contracts/memory.py` 与当前 AST 比较，确认33个原有定义不变；真实四参 canonical request SHA仍为 `6a4c0a68b219e50238694606c3408d5e82b12ac1311e00bcd9816342216b5c21`。

额外脚本输出：`UNCHANGED_EXISTING_CONTRACT_DEFINITIONS 33`；`IHDR_PAIR_MATRIX 15 accepted 65521 rejected`；`EXTRA_NEGATIVE_CONTROLS 65549 PASS`。这些是内存脚本的有限输入控制数量，不是新增 pytest/CI 用例，不扩张功能接受范围。

### 7.5 保留的后续门槛与写回

- **消费者第二阶段仍关闭。** 没有 GenerationMessage.images、image role/count 接入、serializer/image counter、正式编码/manifest/restore、source authority、packing/summary 或 native admission。当前类型定义和未来常量8不授权产品少图/缩图，不使请求获得 supportsImages。
- **旧 text compatibility gate仍约束第二阶段。** 首先分别接受 owner 的 version delta，再同步 additive field 和消费者；不能用当前 isolated DTO 的通过绕过旧 asdict/hash 变更问题。现有 history pure模块和 #43施工仍不动。
- **CI collection未验收。** 本树 `ci.yml:73` 仍只列 instruction/admission/admission_postgres；pytest 默认 testpaths 不含本新文件。controller需要给 CI owner narrow grant 显式收集本59用例并实际运行。此次本地 ACCEPT不声称 hosted CI通过，reviewer不修改 CI。
- **完整源/DB/UI/模型视觉能力未接受。** 无 native PNG pipeline、真实 provider、数据库、paid模型或视觉端到端验证。

原 history review保持 `f14a8a77992665580f9bdd4b07045ac4601892d03cc39251d92865d962f952ec`；history contract/ranges/search及 canonical compaction DTO哈希也重新核对保持。仅追加/更新本review，未改候选/evidence、产品、tests、CI、Git、#43施工、全局/private memory或canonical #40。durable write-back限于此原评审。
