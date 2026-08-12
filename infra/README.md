# Infrastructure

基础设施与部署入口位于 [`docker/README.md`](docker/README.md)：

- 本地开发依赖 Compose
- Web、API、Worker 完整部署 Compose
- 环境变量、迁移门禁、健康检查和运行命令
- Prometheus 指标、Caddy HTTPS 入口和内部端口边界
- PostgreSQL/MinIO 同批备份、空部署恢复与校验门禁

## V5-D mixed acceptance entrypoint (D-OPS)

Thin wrapper (no business contract changes):

```bash
# Cheap static readiness (default): bash -n harnesses + backup/restore unit tests
infra/scripts/run-v5d-mixed-acceptance.sh \
  --output-dir docs/evals/artifacts/v5d-mixed-static-$(date -u +%Y%m%dT%H%M%SZ)

# Optional expensive isolated live lanes (reuses existing runners only)
infra/scripts/run-v5d-mixed-acceptance.sh --mode document --output-dir /tmp/v5d-doc
infra/scripts/run-v5d-mixed-acceptance.sh --mode research --output-dir /tmp/v5d-r800
```

Report schema: [`scripts/v5d-mixed-acceptance.report.schema.json`](scripts/v5d-mixed-acceptance.report.schema.json).

Reuses:

- Document restore: `scripts/run-v5b-document-acceptance.sh` + `docker/compose.v5b.yml`
- Research restore: `scripts/run-r800-acceptance.sh` + `docker/compose.r800.yml`
- Shared backup/restore: `scripts/backup-deployment.sh`, `scripts/restore-deployment.sh`

Mixed PDF/Image/Document **live** seed/snapshot is still blocked until a worker
CLI exists; the wrapper records that gap and never claims model quality or user
value gates.
