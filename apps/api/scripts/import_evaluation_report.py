from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_pdf_api.db.session import SessionLocal
from ai_pdf_api.services.evaluation import (
    EvaluationImportError,
    import_evaluation_report_transactionally,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import one trusted canonical Citeframe evaluation report.")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        report_bytes = args.report.read_bytes()
        result = import_evaluation_report_transactionally(
            SessionLocal,
            workspace_id=args.workspace_id,
            report_bytes=report_bytes,
        )
    except OSError as error:
        parser.error(f"cannot read report: {error}")
    except EvaluationImportError as error:
        parser.error(f"{error.code}: {error.message}")
    print(
        json.dumps(
            {
                "created": result.created,
                "evaluationRunId": result.evaluation_run_id,
                "sourceReportSha256": result.source_report_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
