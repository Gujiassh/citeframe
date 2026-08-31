from __future__ import annotations

import errno
import hashlib
from pathlib import Path

import ai_pdf_worker.r803_evaluation_campaign as campaign
import pytest

pytestmark = pytest.mark.evaluation


def _access_denied(path: Path) -> PermissionError:
    return PermissionError(errno.EACCES, "access denied", str(path))


def test_windows_directory_open_access_denied_is_the_only_unsupported_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "evidence"
    directory.mkdir()
    monkeypatch.setattr(campaign, "_IS_WINDOWS", True)

    def unsupported_open(_path: str, _flags: int) -> int:
        raise _access_denied(directory)

    monkeypatch.setattr(campaign.os, "open", unsupported_open)
    campaign._fsync_directory(directory)


@pytest.mark.parametrize(
    ("is_windows", "error"),
    [
        (False, _access_denied(Path("evidence"))),
        (True, PermissionError(errno.EPERM, "operation not permitted")),
        (True, OSError(errno.EIO, "I/O failure")),
    ],
)
def test_directory_open_unexpected_errors_propagate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    is_windows: bool,
    error: OSError,
) -> None:
    directory = tmp_path / "evidence"
    directory.mkdir()
    monkeypatch.setattr(campaign, "_IS_WINDOWS", is_windows)

    def failing_open(_path: str, _flags: int) -> int:
        raise error

    monkeypatch.setattr(campaign.os, "open", failing_open)
    with pytest.raises(type(error)) as raised:
        campaign._fsync_directory(directory)
    assert raised.value is error


def test_windows_access_denied_for_non_directory_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "not-a-directory"
    path.write_text("content", encoding="utf-8")
    error = _access_denied(path)
    monkeypatch.setattr(campaign, "_IS_WINDOWS", True)

    def failing_open(_path: str, _flags: int) -> int:
        raise error

    monkeypatch.setattr(campaign.os, "open", failing_open)
    with pytest.raises(PermissionError) as raised:
        campaign._fsync_directory(path)
    assert raised.value is error


def test_windows_access_denied_for_directory_symlink_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "directory-link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        if getattr(error, "winerror", None) == 1314:
            pytest.skip("Windows account cannot create the directory symlink")
        raise
    assert link.is_dir()
    assert link.is_symlink()
    error = _access_denied(link)
    monkeypatch.setattr(campaign, "_IS_WINDOWS", True)

    def failing_open(_path: str, _flags: int) -> int:
        raise error

    monkeypatch.setattr(campaign.os, "open", failing_open)
    with pytest.raises(PermissionError) as raised:
        campaign._fsync_directory(link)
    assert raised.value is error


def test_windows_access_denied_for_junction_directory_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "junction-boundary"
    directory.mkdir()
    error = _access_denied(directory)
    monkeypatch.setattr(campaign, "_IS_WINDOWS", True)
    # Creating a real junction is Windows-shell-specific. Path.is_junction() is
    # the production boundary, so simulate only that classification while the
    # path remains a real directory for is_dir() and false for is_symlink().
    monkeypatch.setattr(type(directory), "is_junction", lambda _self: True)
    assert directory.is_dir()
    assert not directory.is_symlink()
    assert directory.is_junction()

    def failing_open(_path: str, _flags: int) -> int:
        raise error

    monkeypatch.setattr(campaign.os, "open", failing_open)
    with pytest.raises(PermissionError) as raised:
        campaign._fsync_directory(directory)
    assert raised.value is error


def test_directory_fsync_unexpected_error_propagates_and_closes_fd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "evidence"
    directory.mkdir()
    closed: list[int] = []
    monkeypatch.setattr(campaign.os, "open", lambda _path, _flags: 73)
    monkeypatch.setattr(campaign.os, "close", closed.append)

    def failing_fsync(_fd: int) -> None:
        raise OSError(errno.EIO, "I/O failure")

    monkeypatch.setattr(campaign.os, "fsync", failing_fsync)
    with pytest.raises(OSError, match="I/O failure"):
        campaign._fsync_directory(directory)
    assert closed == [73]


def test_exclusive_write_keeps_file_fsync_hash_and_refuses_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "round" / "immutable.json"
    content = b'{"status":"started"}\n'
    file_fsyncs: list[int] = []
    directory_fsyncs: list[Path] = []
    monkeypatch.setattr(campaign.os, "fsync", file_fsyncs.append)
    monkeypatch.setattr(campaign, "_fsync_directory", directory_fsyncs.append)

    digest = campaign._write_exclusive_bytes(path, content)

    assert path.read_bytes() == content
    assert digest == hashlib.sha256(content).hexdigest()
    assert len(file_fsyncs) == 1
    assert directory_fsyncs == [path.parent]
    with pytest.raises(FileExistsError):
        campaign._write_exclusive_bytes(path, b"replacement")
    assert path.read_bytes() == content


def test_atomic_json_write_keeps_file_fsync_replace_hash_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "campaign-progress.json"
    path.write_text("old", encoding="utf-8")
    file_fsyncs: list[int] = []
    replacements: list[tuple[Path, Path]] = []
    original_replace = campaign.os.replace
    monkeypatch.setattr(campaign.os, "fsync", file_fsyncs.append)

    def tracked_replace(source: Path, destination: Path) -> None:
        replacements.append((Path(source), Path(destination)))
        original_replace(source, destination)

    monkeypatch.setattr(campaign.os, "replace", tracked_replace)
    digest = campaign._atomic_write_json(path, {"status": "running"})

    content = campaign.canonical_bytes({"status": "running"})
    assert path.read_bytes() == content
    assert digest == hashlib.sha256(content).hexdigest()
    assert len(file_fsyncs) == 1
    assert len(replacements) == 1
    assert replacements[0][1] == path
    assert not replacements[0][0].exists()
    assert list(tmp_path.glob(f".{path.name}.*")) == []
