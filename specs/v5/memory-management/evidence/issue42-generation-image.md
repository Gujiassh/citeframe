# GenerationImage 第一阶段实施证据

日期：2026-09-29。状态：候选冻结，提交原独审实施复核；未自判验收或激活。

批准合同 specs/v5/memory-management/lanes/issue42-generation-image.md：
8f6870b96deb4815161a3fd37676aadc0f11bcfe263213d2ed336d662712e313
批准 review reviews/issue42-generation-image.md：
fbc13e6f724aeb1958e8271e6247c023c9cec13f39f9c8cf08a8520a27d8a2c5

## 精确候选

| 文件 | SHA-256 |
|---|---|
| packages/backend-contracts/src/citeframe_contracts/memory.py | f168652de5a5c103fe177f20f6f747b2db966218772fe650f9e38771b004163d |
| packages/backend-contracts/src/citeframe_contracts/__init__.py | 90096c370eec9ab6452562b844dc0b5a55ce0435138fe6660f8efcfa4f828e25 |
| packages/memory-service/tests/test_generation_image_contract.py | 49e806b7681b76e8dac43ac02e27356dab62551a7909766ff8af4fd7f049003f |

独立 frozen GenerationImage、generation-image-structure-v1 及批准结构常量、有界 validator、单一 export。没有向 GenerationMessage 加 images；所有现存 DTO 字段和逻辑保持原状。GENERATION_MESSAGE_MAX_IMAGES=8 仅声明未来结构常量，未接入 message/native 数量行为。

验证顺序：exact scalar types、O(1) 长度、padding 推导 decoded 长度、一次有界 alphabet 扫描、一次 ASCII/strict decode/encode 等值、固定33-byte IHDR。CRC 输入恰17 bytes。无 Pillow/PDF/I/O、全量 hash、递归或修复重编码。PNG 完整有效性及 upstream 内存/时间仍由 native admission 负责。

## 实际执行

工作目录 D:/Code/citeframe-lanes/issue42-persistence：

~~~powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -m pytest packages/memory-service/tests/test_generation_image_contract.py packages/memory-service/tests/test_admission.py packages/memory-service/tests/test_instruction_memory.py::test_validation_and_fail_closed packages/memory-service/tests/test_instruction_memory.py::test_neutral_import_without_application_packages -q -s -p no:cacheprovider
~~~

实际结果：1664 passed in 10.80s，exit 0，无 skips。
组成：59 image contract、1603 admission、2 P1a validation/import。
此前初始 image 候选：57 passed in 6.63s；之后增加 padding 拒绝及扫描次数/长度前零扫描两项，以上 combined run 为最终候选结果。
git diff --check 通过；仅提示工作树 LF 将来 Git 转 CRLF，无 whitespace error。未进行 Git 写入。

真实边界与 spy：
- B=4,194,304 decoded、E=5,592,408 encoded 正例通过，一次 ASCII encode、一次 decode、一次 encode。
- B+1（单 padding）、B+2（无 padding）都恰 E 字符，在转换前按 D 拒绝；E+1 和短输入同样零转换。
- 转换 spy 与直接构造后的 profile/counter/provider 哨兵均零调用；这些下游哨兵仅证明局部调用顺序，不声称真实 adapter 集成证据。
- 一次有效 alphabet 遍历；E+1 在遍历前拒绝。types、非 ASCII、非法/过量 padding、非 canonical pad bits、截断/伪造 IHDR、CRC、dimensions/整数/bit depth/color/compression/filter/interlace 覆盖。
- 最大结构 dimension 可通过有效 IHDR-only fixture；不执行或声称对应像素解码安全。33-byte IHDR-only 正例按合同通过。
- frozen 赋值拒绝、base64 从 repr/嵌套 repr 隐藏、codec exception 使用 from None；标准 traceback 与 caplog 不含输入 payload。未开启 locals traceback 捕获。

输入在 tracemalloc 启动前预构造；转换 spies 保留调用记录，测量包括这部分测试开销：

| decoded bytes | encoded chars | additional tracked peak bytes |
|---:|---:|---:|
| 33 | 44 | 3,828 |
| 34 | 48 | 3,855 |
| 35 | 48 | 3,848 |
| 65,536 | 87,384 | 287,797 |
| 4,194,304 | 5,592,408 | 18,179,245 |

全部低于33,554,432 bytes（32 MiB）。结果是当前 Python/平台 tracemalloc 的额外 tracked 分配，非 RSS、并发或 native decoder 上界。

## 兼容性及冻结范围

测试断言 GenerationMessage dataclass fields 仍精确为 role/content/tool_calls/tool_call_id；真实四位置参数的 text GenerationRequest canonical SHA：
6a4c0a68b219e50238694606c3408d5e82b12ac1311e00bcd9816342216b5c21
与原审基线相同。没有重写旧 archive 或任何历史 digest。

本轮核对冻结文件：history/ranges.py=65f068f1003692f0b30e4f7f0daa8c4ab3993b2f5fd44c6686163dca93669d08；history/search.py=1e399094f51ae3f4dcfd9c25474584ab85193ce745410fc836704a2433fa334f；history/__init__.py=4c554257bcd2186adba89361614363bdc7ec92c969ccbb200e1ef6027a8dd3a0；contracts/history.py=a771d0caf41ac0da307e1bb723da039aa2411f9cc35dd86e4c2ee460cf9d3c02；contracts/compaction.py=d77617a25ecf5cd9c0b808537f6c884b7ee67e2a2250bb0d955e99597ddb5e2b。未修改这些文件，也未用 sibling policy 路径运行本次测试。

第二阶段 images tuple/role 行为、59测试之外的消费方正式版本 delta、serializer/counter、archive/source/packing、native admission 和真实 image activation 均未实施。8/9 tuple 测试依批准审阅保留到第二阶段。无 schema/CI/branch/Git/其它产品写入，无模型/付费/数据库调用。批准合同和 reviewer 文件未修改。

Durable write-back 限于本 owned evidence；等待原独审对以上精确候选复核。
