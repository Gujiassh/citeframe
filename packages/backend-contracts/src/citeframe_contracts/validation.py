"""Structured agent result validation failure, independent of evaluation storage."""


class AgentResultValidationError(ValueError):
    def __init__(
        self,
        node_key: str,
        rule: str,
        path: str,
        *,
        logical_call_key: str | None = None,
        raw_output_sha256: str | None = None,
    ) -> None:
        self.node_key = node_key
        self.rule = rule
        self.path = path
        self.logical_call_key = logical_call_key
        self.raw_output_sha256 = raw_output_sha256
        self.failure_code = f"{node_key}_invalid_output"
        self.failure_origin: str = "model_or_workflow_quality"
        super().__init__(self.failure_code)
