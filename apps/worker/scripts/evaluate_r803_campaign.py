from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_pdf_worker.r803_evaluation_campaign import run_or_resume_campaign
from ai_pdf_worker.r803_evaluation_contract import (
    DEFAULT_PACKAGE_V5_PATH,
    load_evaluation_package,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run or resume the evaluator-only R803 five-round campaign."
    )
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE_V5_PATH)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--max-new-rounds", type=int)
    parser.add_argument("--baseline-evaluation-run-id")
    args = parser.parse_args()
    report = run_or_resume_campaign(
        campaign_dir=args.campaign_dir,
        package=load_evaluation_package(args.package),
        max_new_rounds=args.max_new_rounds,
        baseline_evaluation_run_id=args.baseline_evaluation_run_id,
    )
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
