# Worker App

后台任务消费者入口。

当前状态：
- 轮询持久化的 `ingestion_jobs` 队列
- 生产 registry 已消费 PDF 和 Image `ingest`；PDF 将页面 layout/OCR/表格/图表/页内图片拆成类型化 ContentUnit，Image 将 canonical PNG、OCR/caption 区域拆成类型化 ContentUnit 并写入 embedding
- 对没有文本层的 PDF 页面使用 RapidOCR fallback，再进入同一页面/文本块链路
- 已支持 `embed_chunks` 回填已有 ContentUnit 与 `delete_cleanup` 原对象/派生对象清理
- Image adapter 已完成 PNG/JPEG/WebP 完整校验、EXIF 方向归一化、canonical PNG、RapidOCR、Responses API caption、区域 ContentUnit 和 text embedding；共享 API Evidence 主链复用图片 Citation/NoteSource，M403B 真实上传、长期 Worker 浏览器链和恢复门禁已通过
- 新建 Asset 任务快照会记录 Workspace 的 `chunkSize`，PDF adapter 按任务快照切块；旧任务缺少该字段时使用 1200 字符默认值

可靠性行为：
- 每次只领取并处理一个 job；API 已知的 PDF、OCR、embedding 业务错误仍由 API 写入 `ingestion_jobs.status=failed`，Worker 不会自动复活旧 job。
- Worker 捕获迭代级基础设施异常，按 `1s -> 2s -> 4s -> 8s` 退避，连续 5 次仍失败后记录 `worker_retry_exhausted` 并以非零状态退出，交由外部进程管理器重启。
- 收到 `SIGINT` 或 `SIGTERM` 后设置停止事件；正在处理的 job 允许自然结束，随后退出，不中断 API 当前的 job 状态事务。
- 日志使用 `ai_pdf_worker` logger，包含 `worker_job_claimed`、`worker_job_handled`、`worker_iteration_failed`、`worker_retry_scheduled`、`worker_fatal` 等平面事件标记，便于按事件名、`job_id`、`error_type` 检索。


本地启动：

```bash
cd /home/cc/code/citeframe
AI_PDF_EMBEDDING_PROVIDER=ollama AI_PDF_EMBEDDING_MODEL=qwen3-embedding:0.6b uv run --python 3.12 --project apps/worker python -m ai_pdf_worker.main
```

本地 metrics 默认只监听 `127.0.0.1:9101`。完整部署由 Compose 显式设置 `AI_PDF_WORKER_METRICS_HOST=0.0.0.0`，但端口只在 Compose 私网 expose，不发布到宿主机。

Worker 使用 RapidOCR + ONNX Runtime 在 CPU 上识别扫描 PDF 页面和 canonical Image Representation。OCR 核心只接受像素并返回中立区域；PDF 与 Image adapter 分别负责 raster/decode 和模态映射。OCR 模型随依赖安装，不会写入仓库；首次处理时会占用更多 CPU 和内存。
`rapidocr-onnxruntime` 自身提供并锁定 OpenCV 依赖，Worker 不再重复安装另一套 `opencv-python-headless`，避免两个发行包覆盖同一 `cv2` 文件。

图片方向归一化直接依赖 Pillow。只接受静态单帧 PNG/JPEG/WebP，完整容器必须无截断或尾随数据，解码格式必须与声明 MIME 一致，EXIF Orientation 必须缺失或位于 1-8，默认上限为 64 MP。输出固定为剥离 EXIF/ICC/附加元数据的 RGB/RGBA canonical PNG；源对象和 `source_sha256` 不改写。


Worker 不会自动切换 embedding provider。`AI_PDF_EMBEDDING_PROVIDER`、`AI_PDF_EMBEDDING_MODEL` 必须和 API 使用同一套索引配置；切换 provider 或版本后，需要重新执行文档 reindex。Image 生产摄取还要求 API 与 Worker 共享 `AI_PDF_IMAGE_CAPTION_*`、`AI_PDF_OPENAI_API_KEY` 和 `AI_PDF_OPENAI_API_BASE` 配置。
