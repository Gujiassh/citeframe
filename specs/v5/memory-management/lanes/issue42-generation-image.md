# GenerationImage 最小共享 ABI 合同

2026-09-29。状态：DESIGN ONLY，提交原独审 a74ed9c2；尚未授权实施或激活。

## 1. 实物依据与边界

只读依据：#44 issue44-chat-loop.md §§16/19/21，SHA-256 39377e36f20476ebc10bd908a0596723a40534a7137fd45c0e78964487946b42。
原生 services/chat.py::_build_generation_user_message 将 prompt 放首位，依次追加 targets 中各 image_payloads，再追加 extra_image_payloads；PNG bytes 原样 base64，detail=high。无图时 content 保持字符串。services/chat_completions.py::chat_messages 保留该顺序并转 image_url；services/providers.py::_map_deepseek_image_part 转 Anthropic base64 source，不带 detail。此次检查本树原生文件哈希：
- chat.py：dd6d28f8629c1655aca238b817ace9be81c4dfb33c4198027b8fe9f966973c91
- chat_completions.py：1de65a326e5f0b7555e0f5251524acb04b92f82d0d1eedeb01aed5d66e9258dee
- providers.py：8338579b25493c2ae1d837fcccd675f8f80b169c7ec22cf04fc9082aa755501e

该增量只承载已获准的原生 PNG 输入。不增加 audience/private 模式、source 类型、远程 URL、通用 content-part union、迁移或模型能力。已接受 shared-history 纯模块及 #43 I3/I4 文件保持冻结。本合同无运行时/CI 接受声明。

## 2. 精确 ABI 提案

沿用 #44 §16 的字符串承载形式，避免 bytes 与 base64 两份可分歧状态：

~~~python
@dataclass(frozen=True)
class GenerationImage:
    media_type: Literal["image/png"]
    data_base64: str = field(repr=False)
    width: int
    height: int
    detail: Literal["high"] = "high"

# 第二阶段才追加；须先接受并同步 §6 的正式消费者 version delta：
images: tuple[GenerationImage, ...] = ()
~~~

不可变性：所有字段为标量，images 必须是 tuple，成员为 GenerationImage；不接受 bytearray、list、可变 Mapping 或原地重编码。data_base64 为非空、标准 RFC4648 alphabet、严格 padding、无空白且 decode→encode 等值的 canonical 表示；decoded bytes 必须保留已获准 PNG 的全部原始字节，包括 metadata。不得归一化像素、重压缩或重新裁剪以“修复”输入。

共享 DTO 验证严格类型、media_type、detail、正整数 width/height（bool 拒绝）及 canonical base64 语法/PNG signature/IHDR dimensions 与字段相符。这些结构检查不证明 PNG 完整可解码；不得在 DTO 构造中启动 Pillow/PDF 解码或 I/O。上游完整有效性与资源边界见 §5。结构错误统一 ProtocolError("generation_input_unsupported")，不含输入/文件/credential 信息；GenerationImage repr 不输出 base64。

仅 role=user 且无 tool_calls、tool_call_id 的消息可有 images；content 仍严格为 str，可为空。system/assistant/tool 有图均拒绝。每个 user message 序列为一个文本 part，随后 images tuple 的原序；不支持图文交错、工具图像结果或 assistant 图像输出。GenerationRequest、ToolCall、GenerationEvent、Usage 不加字段。摘要 purpose 不额外授予图像能力。

### 2.1 GI01：构造验证器的独立结构边界

固定验证规则版本为 **generation-image-structure-v1**；#42 在唯一 memory.py 持有版本及以下命名常量，不由 caller/profile 覆写。它是验证器工程约束的待审定值，由 controller 裁决；不代表用户生产容量、模型能力或已获审 native limits。修改这些值须显式版本变更和对应测试复审。

| 常量 | v1 精确值 |
|---|---:|
| GENERATION_IMAGE_MAX_DECODED_BYTES | 4,194,304（4 MiB，B） |
| GENERATION_IMAGE_MAX_ENCODED_CHARS | 5,592,408（E = 4 × ceil(B/3)） |
| GENERATION_MESSAGE_MAX_IMAGES | 8（第二阶段 images 字段验证） |
| GENERATION_IMAGE_MAX_DIMENSION | 2,147,483,647（PNG 结构整数界限，不是允许解码的像素容量） |

强制检查顺序与工作界限：
1. 先 exact types：data_base64/media_type/detail 为 str，width/height 为 int（拒绝 bool），再校验固定枚举和 1..MAX_DIMENSION。data_base64 只做 O(1) len，要求 44<=n<=E 且 n%4=0。第二阶段先 exact tuple 与 len(images)<=8，再遍历严格 GenerationImage 成员及检查合法 role；超限 tuple 不遍历、不复制、不重验成员。这些门之前不得 ASCII encode、全串扫描/正则/复制/hash 或 base64 转换。
2. 由至多末尾两字符求 padding p∈{0,1,2}，先算 **D=3*(n//4)-p**，要求 33<=D<=B，未过即拒绝。E 对应无 padding 的 D=B+2、单 padding 的 D=B+1，均须在转换前拒绝。随后一次有界字符扫描验证仅标准 alphabet、末尾恰 p 个 '='、其余无 '=' 或非 ASCII；不 strip、不尝试宽松修复。
3. 仅过上述门后执行一次 ASCII encode、一次 strict b64decode(validate=True)、一次 b64encode；用 canonical encoded bytes 等值比较，不再 decode 成全长 str。decoded 长必须恰 D；roundtrip 拒绝非零 pad bits。无重试/递归/全串 regex/hash；工作 O(E+B)，逐图校验，不缓存额外 decoded bytes。
4. PNG 仅检查 decoded 的固定前 **33 bytes**：8-byte signature；首 chunk 大端 length 恰13、type='IHDR'；完整13-byte data 与4-byte CRC；width/height 大端整数与字段一致且在上述区间。校验 CRC32(type+13-byte data)，最多处理17 bytes。IHDR bit-depth/color-type 只接受 PNG 标准组合（0:1/2/4/8/16；2:8/16；3:1/2/4/8；4/6:8/16），compression/filter=0，interlace∈{0,1}。不按声明 chunk length 分配，不遍历后续 chunk、不解压/读取像素。33-byte IHDR-only 输入可通过此结构层；它不证明 IDAT/IEND、后续 CRC、尾随数据或完整 PNG 有效，完整性仍由 native admission 验证。
5. 大缓冲同时存活至多 ASCII bytes(E)、decoded bytes(B)、roundtrip bytes(E)，外加 codec 有界临时空间与固定 header；校验后释放局部引用。实现验收用 tracemalloc（输入先构造，再开始追踪）测 B 上限及较小正常 fixture，要求额外 tracked peak <=32 MiB，否则不得交付，先修正或复审约束。此工程 gate 不是进程 RSS/并发/上游分配证明；原 str/JSON parse/download/PNG encode/native decode/render 的先前分配仍不受 DTO 追溯保护。

所有拒绝统一既定 ProtocolError("generation_input_unsupported")，codec 异常用 from None，不记录 payload 或包含 locals 的 traceback；嵌套 repr 同样不显示图像数据。profile/native/task 后续各自施加更严上限和 aggregate admission，不能用结构通过替代它们。#44 issue44-native-image-bounds.md 仅为未审参考，其 proposed limits 不由本文接受或激活。

GI01 实施测试门（本轮未执行）：B bytes 的 canonical IHDR fixture 正例、B+1/B+2 decoded 反例、E+1 encoded 反例；非 ASCII、内部/多余 padding、非 canonical pad bits；32-byte 截断、伪 length/type、坏 CRC、尺寸不符/非法整数；第二阶段 tuple 8/9 边界。以 spy 验证长度/推导 D 超限路径 **ASCII 转换、完整 decode/encode、counter/profile/provider 调用均为零**；允许纯长度 helper 的小整数边界测试，不能以其替代真实常量边界用例。记录有限正常 fixture 的峰值、一次扫描/转换次数和无 payload error/repr。长度恰 E 且 D 超限用例尤其不能只检查最终报错。

## 3. Source-ref 与原生证据含义

GenerationImage 不新增 source_ref 字段；它是 provider 输入值，不是 source 登记/授权凭据。唯一 SourceReference 继续由 #43 registry 持有，不在 memory.py 复制，也不引入 memory→compaction 的循环类型依赖。

原生 composition/owner43 的现有受控输入 manifest 必须按 (message ordinal,image ordinal) 绑定每幅图：精确原生 object/version、原生 evidence/locator/region snapshot、转换参数及最终 PNG SHA-256，并记录全部真实 source dependencies。裁剪 PNG hash 与原始 PDF/图片 source hash 意义不同；不得把 PNG hash 冒充 source version。相同来源可产生多个有序 crop；不得去重或猜测 refs。没有真实已授权登记 seam 时拒绝激活该请求，不构造假 ref。这个绑定由原 owner 提出其实际 manifest 的最小版本化增量并独审，本文不发明第二登记表或可构造 authority DTO。

在 read、archive restore、summary 输入及 dispatch/adoption 前消费实际 source/ref 和全输出读者授权；图像 DTO、哈希或旧快照均不绕过当前权限/版本/失效检查。来源缺失、删除、撤权、版本或 crop 绑定不符时 fail closed，不回退 OCR/文字或跳过该图。

## 4. 兼容性与消费者

旧四位置参数及所有 text-only 构造保留；images 默认空 tuple。追加 dataclass 字段会改变裸 asdict 输出，不能宣称裸 asdict 字节兼容。

| Owner / consumer | 必须满足的增量 |
|---|---|
| #42 memory.py 与 contracts/__init__.py exports | 唯一 GenerationImage 定义、追加 images、结构/role 验证和共享 contract tests；无 provider serializer 或 registry 实现 |
| #44 adapters serializer/counter | 空 images 的旧 wire payload 字节/形状不变；有图按 Responses input_text/input_image(data URL,high)、ChatCompletions text/image_url(data URL,high)、Anthropic text/image source(base64,image/png) 编码；Anthropic 不伪造 detail。现有 endpoint/header/parser 不改 |
| #43 archive/journal/requests/restore | 旧 text canonical/hash schema 写出继续省略 images，旧 reader 缺字段得到 ()，禁止重算既有 digest。image-bearing request 用明确的新 encoding version、完整保存 canonical 图像字段并严格恢复；未知 version/字段或不支持 images 拒绝，禁止四参数构造静默丢图。旧 tool_group 仍只允许文字，不因 DTO 增量改其字节/hash |
| #43 packing/rendering/summary/checkpoint | 保留图像整单元及 sources；保护当前问题。初期图像单元不进入 text-only 摘要器，也不以 content 代替图像；可保留原单元，装不下明确容量失败。将来 image-aware summary 需另行 profile/count/provenance 接受。checkpoint 不把图像转换为无来源文字 |
| #42 冻结 history 的未来请求 hashing/count 消费 | 当前 asdict(request) 会受新增空字段影响；未经单独 owner 授权不改已接受模块。ABI 集成前须逐消费者核验旧 text digest，并明确版本/兼容投影；不能先升级 ABI 后让旧 digest 悄然改变 |

#44 counter 对实际完整请求计入文字、tools、全部图像及协议 framing，base64 字符数不充当 image token 数。只有已审 profile 明确 supportsImages、尺寸/数量/字节上限及 accountingVersion/maxTokensPerImage 时才接受；固定上界估算标 estimated，exact 需实际 provider/model-specific 算法证据。统计用 redacted base64 projection 只存在于 counter 内；最终 request/hash/archive/send 保留原 payload。未知 profile、缺计数上界、超限或 counter/config mismatch 在发送前稳定失败，无网络调用。本文不修改已接受 profile/adapter，也不填生产默认值或数值容量。

#43 负责完整 request hash 与 archive/restart 等值、真实 source binding 和字节额度；图像解码后的 PNG 字节、base64 膨胀、JSON/完整请求和 archive 各有明确上限，禁止全局解除原限制。旧 reader/packer 尚未支持时 image-bearing 路径保持关闭；text-only 不因图像未激活而改协议。

## 5. 上游前置边界与验收

#44 §21 的 native source-read/decode/render admission 是独立必要前置：读取前授权、增量读取 per-object/task 上限与超限检测、并发总额、解码前像素/内存检查、PDF 首次 pixmap 前几何预算、硬内存/时间边界、PNG 编码输出及操作总额。DTO 只看到最终值，不能阻止此前无界 response.read/image.load/get_pixmap；本 ABI 不接受这种事后限制作为上游安全证据。生产 limits 仍由原 native owner 测量和独审。显式 targets/regions 与 retrieved crops 必须共享预算并保留顺序；不得静默少图/缩图。

独审通过后的最小证据：
1. #42：旧四参构造、不可变性、canonical base64、严格类型/role/detail/PNG dimensions、无 payload errors/repr、单一 export。
2. #44：实际 native fixture 的 bytes/order/high 三协议 parity；空 images 原 payload 等值；无能力/非法图/超限零发送；真实 counter profile 上界与完整 framing、credential-free provenance。
3. #43：旧 text archive/hash fixtures 不变；图像 request 保存/重启字节与 refs 等值；unknown version/丢字段拒绝；保护单元及容量拒绝；撤权/删除 suppression。不以只读 sibling 单测冒充集成 CI。
4. Native owner：§21 pre-allocation/aggregate/admission 真实证据；接受后再跑正常 text+image 答复与重启链路。安全拒绝测试不代表视觉成功路径已经等价。

## 6. 明确 handoff

原独审 a74ed9c2 定向复审 GI01。实施顺序固定：
1. 通过后 controller 可先授予 #42 **独立 GenerationImage 定义/bounded validator/export/专有 tests**；不向现用 GenerationMessage 追加 images，不改变 text asdict/hash。
2. #44 serializer/counter、#43 legacy projection/request encoding/archive restore/source manifest/packing、#42 history hashing 的**正式 version delta 先分别提交并获审**；history 仍冻结，修改须另给 narrow grant。随后 controller 串行同步消费者与 GenerationMessage.images 字段，避免混合旧 reader。仅关闭 images activation 或限定空 tuple 不能保持旧 text digest。
3. 同步版本的旧 text/hash/archive 回归和 image restore/count 通过后，仍须 native admission 与真实权限/parity 门才可激活。

#43 现有 I3/I4 工作不转交；本修订不批准任何未审 native bounds 候选或消费者实现。

本轮仅定向修订本合同 GI01 与必要实施顺序；未改 ABI、profile、adapter、history、DTO/policy/登记文件、schema、CI 或 Git。无模型调用、commit/push。Durable write-back 限于本文件。
