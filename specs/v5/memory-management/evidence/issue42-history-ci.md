# History / GenerationImage pure CI 闭环候选

2026-09-29。当前源与 workflow 已获原独审 fresh bounded ACCEPT，见下方验收补记；无 hosted CI 接受声明。

## 本轮三个文件

- .github/workflows/memory-history-contracts.yml
  SHA-256 f62da08e231908e699158aee4c9e7a9dc34285d6576f2d9d8b7f4ffd97abc318
- packages/memory-service/tests/test_history_sources.py
  SHA-256 737a5a85b8aa46331790b4cfe83c9e0302c72894e8352bc5b73788f7f5f6daee
- 本 evidence。

原修改脚本意图是删除临时 imports/loader；旧22ec原文件无可验证副本，历史精确 diff 无法恢复，撤回“已证明仅删除 loader、42 项正文和断言未变”的确定性说法。当前文件已无 sibling loader；接受依据是当前完整 source 的独立语义审查，不是历史等值。新 workflow 是独立 ubuntu job，不修改 shared ci.yml。push main / pull_request 均触发，无路径过滤、continue-on-error、条件 bypass 或服务依赖。

## Workflow gate

1. checkout 当前提交；uv sync --project apps/api --frozen --extra dev。
2. uv run --project apps/api --frozen --no-sync python 执行内嵌 runner；不取其它 commit、不下载 sibling、不注入替代依赖。
3. 运行前后核验七个关键模块的实际 __file__ 等于本 checkout 精确路径：contracts memory/compaction/history，memory compaction init/policy 和 history ranges/search。
4. 两个 test 文件必须存在；收集文件计数精确 42+59，101 唯一 nodeids；skip/skipif/xfail marker 拒绝。
5. 每个 nodeid 必须恰有 passed setup/call/teardown；任何 skipped、wasxfail、未执行、缺阶段、重复阶段或 pytest 非零退出均失败。禁用自动第三方 plugin loading，拒绝 PYTEST_ADDOPTS 与 sibling 环境变量。没有 broad directory collection。

## 实测与环境限制

本机尝试 uv sync --project apps/api --frozen --extra dev 失败：启动已安装 uv.exe 时 OS 报“拒绝访问”，未完成 frozen sync。没有改用其它路径绕过此限制；本 tree 无 apps/api/.venv。本地验证不能称为 frozen API environment / hosted CI 通过。controller/hosted runner 仍需执行 workflow 的真实 frozen install+run。

实际局部验证：使用 D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B，PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1，PYTHONPATH 仅显式指向本 checkout packages/backend-contracts/src、memory-service/src、backend-persistence/src。从新 workflow 的 python heredoc 原样提取执行（仅去 YAML 十空格缩进），没有运行替代测试 runner。

输出：七个模块运行前后均 checkout-import；101 passed in 6.23s，exit 0；pure-contracts-executed=101; history=42; generation-image=59; skipped=0; xfailed=0。本地 interpreter 是现有 API 环境；产品模块来自本 checkout，未使用 sibling。

另对同一 inline ExactRun gate 做合成 report 负例：skip、xfail、not_run、missing_teardown、duplicate_call、missing_collection 六项都被拒绝。这是 gate 判定逻辑探针，不代替 actual pytest run；actual 101 项结果如上。先前 admission/P1a 本地回归仍保留在 issue42-generation-image.md，本轮不重跑/新增到 CI。

## 不变依赖与冻结文件

controller 集成的原 #43 文件，本轮只读，前后哈希一致：
- compaction/policy.py：f992b4d5e0d512a6cae7756cab3ed0e33def8f178a4948c05a919dc9b2796b44
- compaction/__init__.py：2026cc0cd44d5f3475f58b0abee0a8f6531328d3e24ffb992150202cec5bdd0a
- contracts/compaction.py：d77617a25ecf5cd9c0b808537f6c884b7ee67e2a2250bb0d955e99597ddb5e2b

GenerationImage 原审三个候选未改：
- contracts/memory.py：f168652de5a5c103fe177f20f6f747b2db966218772fe650f9e38771b004163d
- contracts/__init__.py：90096c370eec9ab6452562b844dc0b5a55ce0435138fe6660f8efcfa4f828e25
- tests/test_generation_image_contract.py：49e806b7681b76e8dac43ac02e27356dab62551a7909766ff8af4fd7f049003f

没有 history 产品代码、DTO、policy、native/source/index/runtime、shared CI、其它产品或原审文件修改。没有 Git/branch/commit/push、模型或付费调用。完整 source issuer/index/runtime 和图像激活均未启用。仅本 evidence 作 durable write-back；controller 后续分组提交及 hosted gate，原 reviewer 接受结论尚待返回。


## 2026-09-29 验收补记：当前源独立接受

原审 reviews/issue42-history-ci.md SHA-256：
8d7b9e82d93a8efe179eeee33c1f22ffe03f0d5cd5fc4c782d51d1d89f121b84，§8 fresh bounded ACCEPT。
对象仍为 test_history_sources.py 737a5a85b8aa46331790b4cfe83c9e0302c72894e8352bc5b73788f7f5f6daee 与 workflow f62da08e231908e699158aee4c9e7a9dc34285d6576f2d9d8b7f4ffd97abc318。

独审完整阅读当前19个函数、fixtures/参数及42项展开语义；复用同哈希的101实际通过（reviewer 6.71s）与真实skip/deselection拒绝；另独立验证20页累积完整tool批次、固定窗口[3,4277)、最终62条messages、同cursor容量拒绝后重预算恢复，以及24项稳定错误反例。20页/24反例是 reviewer 内存控制，未声称已加入CI。

旧22ec11d67fe74a221b38dbed6a0a3d39fda538d5e1f7f09c66dd661f7883b944身份及旧结果保留作历史记录，不能证明与现源逐字节或正文等值。未匹配不构成正文已改变的证据；不再以寻找旧原件阻挡交付。本文前面“等待原 reviewer”是提交时状态，由本节当前接受状态更新。

已接受范围为 pure-history、checkout依赖及该独立CI接入；独立GenerationImage第一阶段接受仍以其原review为准。frozen install/hosted job尚待实际成功；source issuer/index/native权限/DB/runtime和图像激活未接受。本次仅文档收窄，无产品/test/workflow改动。
