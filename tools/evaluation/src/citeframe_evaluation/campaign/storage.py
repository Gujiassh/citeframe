from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from citeframe_evaluation.contracts import (
    R803EvaluationError,
    canonical_bytes,
    file_sha256,
)
from citeframe_evaluation.integrity import list_regular_files_relative
from citeframe_evaluation.campaign.plan import (
    CampaignPlan,
    PROGRESS_SCHEMA_VERSION,
    ROUND_START_SCHEMA_VERSION,
    _plan_provenance_fields,
)


_IS_WINDOWS = os.name == "nt"


def _fsync_directory(directory: Path) -> None:
    try:
        dir_fd = os.open(str(directory), os.O_RDONLY)
    except PermissionError as error:
        # Windows' CRT cannot open directory handles through os.open. This is a
        # platform capability gap, not permission to suppress arbitrary I/O errors.
        if (
            _IS_WINDOWS
            and error.errno == errno.EACCES
            and directory.is_dir()
            and not directory.is_symlink()
            # Python 3.12 reports Windows directory junctions separately from
            # symlinks. They are reparse points rather than the real directory
            # for which this narrow CRT capability exception is intended.
            and not directory.is_junction()
        ):
            return
        raise
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _write_exclusive_bytes(path: Path, content: bytes) -> str:
    """Exclusive create with file data + parent directory durability."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as target:
        target.write(content)
        target.flush()
        os.fsync(target.fileno())
    _fsync_directory(path.parent)
    return hashlib.sha256(content).hexdigest()


def _write_immutable_json(path: Path, value: object) -> str:
    return _write_exclusive_bytes(path, canonical_bytes(value))


def _atomic_write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = canonical_bytes(value)
    digest = hashlib.sha256(content).hexdigest()
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return digest


def _write_round_start_marker(
    round_dir: Path,
    plan: CampaignPlan,
    *,
    round_index: int,
    attestation: dict[str, object],
) -> str:
    marker = {
        "schemaVersion": ROUND_START_SCHEMA_VERSION,
        "roundIndex": round_index,
        **_plan_provenance_fields(plan),
        "providerAttestation": attestation,
        "startedAt": datetime.now(UTC).isoformat(),
        "status": "started",
    }
    path = round_dir / "round-start.json"
    digest = _write_immutable_json(path, marker)
    _write_immutable_json(round_dir / "round-start.sha256.json", {"sha256": digest})
    return digest


def _round_is_complete(round_dir: Path) -> bool:
    return (round_dir / "SHA256SUMS").is_file() and (
        round_dir / "round-report.json"
    ).is_file()


def _round_is_started(round_dir: Path) -> bool:
    return (round_dir / "round-start.json").is_file() or (
        round_dir.exists() and any(round_dir.iterdir())
    )


def _partial_round_file_hashes(round_dir: Path) -> dict[str, str]:
    return {
        name: file_sha256(round_dir / name)
        for name in list_regular_files_relative(
            round_dir,
            include_checksum_manifest=True,
        )
    }


def _write_progress_snapshot(campaign_dir: Path, report: dict[str, Any]) -> None:
    progress = {
        "schemaVersion": PROGRESS_SCHEMA_VERSION,
        "mutable": True,
        "status": report["status"],
        "sample": report["sample"],
        "gates": {
            "engineering": report["gates"]["engineering"],
            "modelQuality": report["gates"]["modelQuality"],
            "modelQualityReason": report["gates"]["modelQualityReason"],
            "userValue": report["gates"]["userValue"],
            "productStage": report["gates"]["productStage"],
        },
        "completedRoundIndexes": [item["roundIndex"] for item in report["rounds"]],
        "updatedAt": datetime.now(UTC).isoformat(),
    }
    _atomic_write_json(campaign_dir / "campaign-progress.json", progress)


def _supersede_progress_if_present(campaign_dir: Path, terminal_digest: str) -> None:
    progress_path = campaign_dir / "campaign-progress.json"
    if not progress_path.exists():
        return
    existing = json.loads(progress_path.read_text(encoding="utf-8"))
    superseded = {
        **existing,
        "mutable": False,
        "supersededBy": "campaign-report.json",
        "supersededBySha256": terminal_digest,
        "supersededAt": datetime.now(UTC).isoformat(),
        "status": "superseded",
    }
    _atomic_write_json(progress_path, superseded)


def _write_terminal_campaign_report(campaign_dir: Path, report: dict[str, Any]) -> str:
    if report["status"] not in {"completed", "failed"}:
        raise R803EvaluationError("campaign_report_requires_terminal_status")
    report_path = campaign_dir / "campaign-report.json"
    digest = _write_immutable_json(report_path, report)
    companion_path = campaign_dir / "campaign-report.sha256.json"
    if not companion_path.exists():
        _write_immutable_json(companion_path, {"sha256": digest})
    else:
        existing = json.loads(companion_path.read_text(encoding="utf-8"))
        if existing.get("sha256") != digest:
            raise R803EvaluationError("campaign_report_companion_conflict")
    _supersede_progress_if_present(campaign_dir, digest)
    return digest


_ROUND_DIR_RE = re.compile(r"^round-(\d{2})$")


def _discover_nonempty_round_dirs(campaign_dir: Path) -> list[tuple[int, Path]]:
    """Return sorted nonempty round directories; reject malformed/out-of-band names.

    Any round-* entry that is a symlink or not a real directory is rejected,
    including empty symlink roots.
    """
    found: list[tuple[int, Path]] = []
    if not campaign_dir.exists():
        return found
    for entry in sorted(campaign_dir.iterdir(), key=lambda item: item.name):
        if not entry.name.startswith("round-"):
            continue
        match = _ROUND_DIR_RE.fullmatch(entry.name)
        if match is None:
            raise R803EvaluationError(f"malformed_round_directory:{entry.name}")
        if entry.is_symlink():
            raise R803EvaluationError(f"round_symlink_forbidden:{entry.name}")
        if not entry.is_dir():
            raise R803EvaluationError(f"round_directory_invalid_state:{entry.name}")
        # Empty real directories are ignored; empty/nonempty symlink already rejected.
        if not any(entry.iterdir()):
            continue
        index = int(match.group(1))
        found.append((index, entry))
    return found


def _validate_round_inventory(
    campaign_dir: Path,
    plan: CampaignPlan,
) -> list[tuple[int, Path]]:
    """Validate all nonempty round-* directories before resume/freeze/provider work."""
    discovered = _discover_nonempty_round_dirs(campaign_dir)
    for index, _path in discovered:
        if index < 1 or index > plan.planned_rounds:
            raise R803EvaluationError(f"round_index_out_of_range:{index}")
    if not discovered:
        return []
    indexes = [index for index, _path in discovered]
    expected = list(range(1, max(indexes) + 1))
    if indexes != expected:
        missing = sorted(set(expected) - set(indexes))
        if missing:
            raise R803EvaluationError(f"round_order_violation:gap_before_{missing[0]}")
        raise R803EvaluationError("round_order_violation")
    return discovered
