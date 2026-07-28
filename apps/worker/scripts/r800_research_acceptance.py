"""Thin CLI for Citeframe R800 Research acceptance seed/scenarios/snapshot/verify."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_pdf_api.db.session import SessionLocal
from ai_pdf_api.services.storage import (
    build_storage_client,
    delete_object_if_exists,
    ensure_bucket_exists,
    upload_bytes,
)
from ai_pdf_worker.r800_acceptance_fixture import seed_state
from ai_pdf_worker.r800_acceptance_scenarios import run_scenarios
from ai_pdf_worker.r800_acceptance_snapshot import snapshot_state, verify_snapshots


def _write_json(value: object, output: Path | None = None) -> None:
    rendered = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Citeframe R800 Research acceptance.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seed")
    subparsers.add_parser("run-scenarios")
    subparsers.add_parser("snapshot")
    verify = subparsers.add_parser("verify")
    verify.add_argument("--before", type=Path, required=True)
    verify.add_argument("--after", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "seed":
        ensure_bucket_exists(build_storage_client())
        _write_json(
            seed_state(
                SessionLocal,
                uploader=upload_bytes,
                cleanup=delete_object_if_exists,
            )
        )
        return 0
    if args.command == "run-scenarios":
        _write_json(run_scenarios())
        return 0
    if args.command == "snapshot":
        _write_json(snapshot_state())
        return 0
    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    result = verify_snapshots(before, after)
    _write_json(result, args.output)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
