from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_pdf_worker.r803_evaluation import run_paired_evaluation, write_result
from ai_pdf_worker.r803_evaluation_contract import (
    DEFAULT_PACKAGE_PATH,
    load_evaluation_package,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the provider-backed Citeframe R803 paired evaluation.")
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE_PATH)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline-evaluation-run-id")
    args = parser.parse_args()
    result = run_paired_evaluation(
        package=load_evaluation_package(args.package),
        baseline_evaluation_run_id=args.baseline_evaluation_run_id,
    )
    hashes = write_result(result, args.output_dir)
    print(
        json.dumps(
            {
                "comparisonKeysMatch": result.paired_report["comparisonKeysMatch"],
                "gates": result.paired_report["gates"],
                "hashes": hashes,
                "outputDir": str(args.output_dir),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
