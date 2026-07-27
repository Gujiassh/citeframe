from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_pdf_api.services.r100_evaluation import DEFAULT_BASELINE, DEFAULT_CASES, DEFAULT_OUTPUT, evaluate


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic V4 R100 fixture/scorer/Quick-baseline gate.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = evaluate(args.cases, args.baseline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
