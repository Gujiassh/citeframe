from __future__ import annotations

import multiprocessing
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from ai_pdf_api.core.metrics import STORAGE_OPERATIONS
from ai_pdf_api.services import storage
from minio.error import S3Error
from minio.helpers import get_part_info


def _hang_publication_storage_child(connection: Any, _request: object) -> None:
    try:
        time.sleep(60)
    finally:
        connection.close()


def _unsafe_error_publication_storage_child(
    connection: Any,
    request: storage._PublicationStorageRequest,
) -> None:
    try:
        connection.send(
            ("error", f"RuntimeError:{request.secret_key}:{request.endpoint}")
        )
    finally:
        connection.close()


def _late_side_effect_publication_storage_child(
    connection: Any,
    request: storage._PublicationStorageRequest,
) -> None:
    Path(request.prefix).write_text(str(os.getpid()), encoding="utf-8")
    time.sleep(1.0)
    Path(request.object_key).write_text("late-side-effect", encoding="utf-8")
    connection.send(("ok", None))
    connection.close()


def _run_orphaned_storage_supervisor(
    started_path: str,
    late_path: str,
    secret: str,
) -> None:
    request = storage._PublicationStorageRequest(
        operation="put",
        endpoint="unused.invalid:9000",
        access_key="unused-access",
        secret_key=secret,
        secure=False,
        bucket="unused-bucket",
        object_key=late_path,
        prefix=started_path,
    )
    storage._run_publication_storage_process(
        request,
        deadline_seconds=2.0,
        process_target=_late_side_effect_publication_storage_child,
    )


def _process_is_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        synchronize = 0x00100000
        wait_timeout = 0x00000102
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == wait_timeout
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _process_command_line(pid: int) -> str:
    if os.name == "nt":
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}').CommandLine",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
        return completed.stdout
    proc_cmdline = Path(f"/proc/{pid}/cmdline")
    if proc_cmdline.exists():
        return proc_cmdline.read_bytes().replace(b"\0", b" ").decode(errors="replace")
    completed = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        check=False,
        text=True,
        timeout=5,
    )
    return completed.stdout


class CaptureConnection:
    def __init__(self) -> None:
        self.messages: list[object] = []
        self.closed = False

    def send(self, message: object) -> None:
        self.messages.append(message)

    def close(self) -> None:
        self.closed = True


class FakeResponse:
    def __init__(self) -> None:
        self.reads = 0

    def read(self, _chunk_size: int) -> bytes:
        self.reads += 1
        return b"first" if self.reads == 1 else b"second"

    def close(self) -> None:
        return None

    def release_conn(self) -> None:
        return None


class FakeClient:
    def get_object(self, _bucket: str, _key: str) -> FakeResponse:
        return FakeResponse()


def test_storage_stream_records_cancelled_outcome(monkeypatch) -> None:
    monkeypatch.setattr(storage, "build_storage_client", FakeClient)
    cancelled = STORAGE_OPERATIONS.labels(operation="stream", outcome="cancelled")
    success = STORAGE_OPERATIONS.labels(operation="stream", outcome="success")
    before_cancelled = cancelled._value.get()
    before_success = success._value.get()

    stream = storage.stream_bytes("object.pdf")
    assert next(stream) == b"first"
    stream.close()

    assert cancelled._value.get() == before_cancelled + 1
    assert success._value.get() == before_success


def test_delete_objects_with_prefix_lists_and_removes_every_matching_object(monkeypatch) -> None:
    class Item:
        def __init__(self, object_name: str) -> None:
            self.object_name = object_name

    class PrefixClient:
        def __init__(self) -> None:
            self.removed: list[str] = []

        def list_objects(self, bucket: str, *, prefix: str, recursive: bool):
            assert bucket == storage.settings.minio_bucket
            assert prefix == "workspaces/ws/assets/asset/"
            assert recursive is True
            return iter(
                (
                    Item("workspaces/ws/assets/asset/original.png"),
                    Item("workspaces/ws/assets/asset/representations/1/image-oriented.png"),
                )
            )

        def remove_object(self, bucket: str, object_key: str) -> None:
            assert bucket == storage.settings.minio_bucket
            self.removed.append(object_key)

    client = PrefixClient()
    monkeypatch.setattr(storage, "build_storage_client", lambda: client)

    storage.delete_objects_with_prefix("workspaces/ws/assets/asset/")

    assert client.removed == [
        "workspaces/ws/assets/asset/original.png",
        "workspaces/ws/assets/asset/representations/1/image-oriented.png",
    ]


def test_publication_upload_uses_one_bounded_part_at_the_payload_limit(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class PublicationClient:
        def bucket_exists(self, _bucket: str) -> bool:
            return True

        def put_object(self, _bucket: str, _key: str, _stream: object, **kwargs: object) -> None:
            calls.append(dict(kwargs))

    connection = CaptureConnection()
    monkeypatch.setattr(
        storage,
        "_publication_client_for_request",
        lambda _request: PublicationClient(),
    )
    payload = b"x" * storage.PUBLICATION_MAX_PAYLOAD_BYTES
    request = storage._publication_request(
        "put",
        object_key="research/run/publication/1/final.md",
        payload=payload,
        content_type="text/markdown",
    )

    storage._publication_storage_child(connection, request)

    assert calls == [
        {
            "length": len(payload),
            "content_type": "text/markdown",
            "part_size": storage.PUBLICATION_UPLOAD_PART_SIZE_BYTES,
        }
    ]
    assert connection.messages == [("ok", None)]
    assert connection.closed is True
    assert get_part_info(
        len(payload), storage.PUBLICATION_UPLOAD_PART_SIZE_BYTES
    ) == (storage.PUBLICATION_UPLOAD_PART_SIZE_BYTES, 1)


def test_publication_put_observation_window_covers_every_non_retrying_request() -> None:
    assert storage.PUBLICATION_STORAGE_MAX_LOGICAL_SECONDS == (
        storage.PUBLICATION_STORAGE_HARD_DEADLINE_SECONDS
        + storage.PUBLICATION_STORAGE_TERMINATE_GRACE_SECONDS
        + storage.PUBLICATION_STORAGE_KILL_GRACE_SECONDS
    )
    assert (
        storage.PUBLICATION_ORPHAN_OBSERVATION_SECONDS
        > storage.PUBLICATION_STORAGE_MAX_LOGICAL_SECONDS
    )


def test_publication_storage_runner_enforces_hard_deadline_and_reaps_child(
    monkeypatch,
) -> None:
    monkeypatch.setattr(storage, "PUBLICATION_STORAGE_TERMINATE_GRACE_SECONDS", 0.2)
    monkeypatch.setattr(storage, "PUBLICATION_STORAGE_KILL_GRACE_SECONDS", 0.2)
    request = storage._publication_request("list", prefix="research/run/")
    before_pids = {process.pid for process in multiprocessing.active_children()}
    started = time.monotonic()

    with pytest.raises(TimeoutError, match="^publication_storage_hard_timeout$"):
        storage._run_publication_storage_process(
            request,
            deadline_seconds=0.25,
            process_target=_hang_publication_storage_child,
        )

    assert time.monotonic() - started < 2.0
    leaked = [
        process
        for process in multiprocessing.active_children()
        if process.pid not in before_pids
        and process.name.startswith("publication-storage-")
    ]
    assert leaked == []


def test_publication_storage_child_watchdog_enforces_its_own_monotonic_deadline() -> None:
    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=False)
    request = storage._publication_request("list", prefix="research/run/")
    process = context.Process(
        target=storage._publication_storage_child_entry,
        args=(
            child_connection,
            request,
            time.monotonic() + 0.3,
            os.getpid(),
            _hang_publication_storage_child,
        ),
        name="publication-storage-watchdog-deadline-test",
        daemon=True,
    )
    try:
        process.start()
        child_connection.close()
        process.join(timeout=2)
        assert not process.is_alive()
        assert process.exitcode == storage.PUBLICATION_STORAGE_WATCHDOG_EXIT_CODE
    finally:
        parent_connection.close()
        child_connection.close()
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)


def test_publication_storage_child_self_terminates_when_supervisor_is_killed(
    tmp_path: Path,
) -> None:
    started_path = tmp_path / "child-started.txt"
    late_path = tmp_path / "late-side-effect.txt"
    secret = "storage-secret-must-not-appear-in-argv"
    context = multiprocessing.get_context("spawn")
    supervisor = context.Process(
        target=_run_orphaned_storage_supervisor,
        args=(str(started_path), str(late_path), secret),
        name="publication-storage-supervisor-test",
    )
    child_pid: int | None = None
    try:
        supervisor.start()
        wait_until = time.monotonic() + 5.0
        while not started_path.exists() and time.monotonic() < wait_until:
            time.sleep(0.02)
        assert started_path.exists()
        child_pid = int(started_path.read_text(encoding="utf-8"))
        assert _process_is_alive(child_pid)
        assert secret not in _process_command_line(child_pid)

        supervisor.terminate()
        supervisor.join(timeout=2)
        assert not supervisor.is_alive()

        child_deadline = time.monotonic() + 2.5
        while _process_is_alive(child_pid) and time.monotonic() < child_deadline:
            time.sleep(0.02)
        assert not _process_is_alive(child_pid)

        # The simulated storage callback would land after one second without the
        # child-local watchdog. Wait beyond that point to prove it stayed absent.
        time.sleep(1.1)
        assert not late_path.exists()
    finally:
        if supervisor.is_alive():
            supervisor.terminate()
            supervisor.join(timeout=2)
        if child_pid is not None and _process_is_alive(child_pid):
            os.kill(child_pid, signal.SIGTERM)


def test_publication_storage_runner_does_not_expose_child_error_payload() -> None:
    request = storage._PublicationStorageRequest(
        operation="get",
        endpoint="private-storage.invalid:9000",
        access_key="private-access",
        secret_key="private-secret",
        secure=False,
        bucket="private-bucket",
        object_key="private-object",
        payload=b"private-payload",
    )

    with pytest.raises(RuntimeError) as raised:
        storage._run_publication_storage_process(
            request,
            deadline_seconds=2.0,
            process_target=_unsafe_error_publication_storage_child,
        )

    message = str(raised.value)
    assert message == "publication_storage_failed:UnknownError"
    assert request.endpoint not in message
    assert request.access_key not in message
    assert request.secret_key not in message
    assert request.payload.decode() not in message


def test_publication_storage_child_returns_only_exception_class(monkeypatch) -> None:
    request = storage._PublicationStorageRequest(
        operation="get",
        endpoint="private-storage.invalid:9000",
        access_key="private-access",
        secret_key="private-secret",
        secure=False,
        bucket="private-bucket",
        object_key="private-object",
        payload=b"private-payload",
    )
    connection = CaptureConnection()

    def raise_sensitive_error(_request: object) -> object:
        raise RuntimeError(
            f"{request.endpoint}:{request.access_key}:{request.secret_key}:"
            f"{request.payload.decode()}"
        )

    monkeypatch.setattr(
        storage,
        "_publication_client_for_request",
        raise_sensitive_error,
    )

    storage._publication_storage_child(connection, request)

    assert connection.messages == [("error", "RuntimeError")]
    assert connection.closed is True


def test_publication_download_rejects_oversize_response_without_reading_remainder(
    monkeypatch,
) -> None:
    class OversizeResponse:
        def __init__(self) -> None:
            self.read_amounts: list[int] = []
            self.closed = False
            self.released = False

        def read(self, amount: int) -> bytes:
            self.read_amounts.append(amount)
            return b"x" * amount

        def close(self) -> None:
            self.closed = True

        def release_conn(self) -> None:
            self.released = True

    class OversizeClient:
        def __init__(self, response: OversizeResponse) -> None:
            self.response = response

        def get_object(self, _bucket: str, _key: str) -> OversizeResponse:
            return self.response

    response = OversizeResponse()
    connection = CaptureConnection()
    monkeypatch.setattr(
        storage,
        "_publication_client_for_request",
        lambda _request: OversizeClient(response),
    )

    storage._publication_storage_child(
        connection,
        storage._publication_request("get", object_key="oversize"),
    )

    assert response.read_amounts == [storage.PUBLICATION_MAX_PAYLOAD_BYTES + 1]
    assert response.closed is True
    assert response.released is True
    assert connection.messages == [("error", "ValueError")]
    assert connection.closed is True


@pytest.mark.parametrize("operation", ["list", "delete"])
@pytest.mark.parametrize("error_code", ["NoSuchBucket", "NoSuchKey", "NoSuchObject"])
def test_publication_storage_missing_objects_are_idempotently_absent(
    monkeypatch,
    operation: str,
    error_code: str,
) -> None:
    class MissingClient:
        def list_objects(self, *_args, **_kwargs):
            raise S3Error(None, error_code, "sensitive", None, None, None)

        def remove_object(self, *_args, **_kwargs) -> None:
            raise S3Error(None, error_code, "sensitive", None, None, None)

    request = storage._publication_request(
        operation,
        prefix="research/run/",
        object_key="research/run/generation/final.md",
    )
    connection = CaptureConnection()
    monkeypatch.setattr(
        storage,
        "_publication_client_for_request",
        lambda _request: MissingClient(),
    )

    storage._publication_storage_child(connection, request)

    expected_result = [] if operation == "list" else None
    assert connection.messages == [("ok", expected_result)]
    assert connection.closed is True


def test_publication_storage_adapters_build_explicit_requests(monkeypatch) -> None:
    requests: list[storage._PublicationStorageRequest] = []

    def run(request: storage._PublicationStorageRequest) -> object:
        requests.append(request)
        if request.operation == "get":
            return b"payload"
        if request.operation == "list":
            return ["research/run/generation/final.md"]
        return None

    monkeypatch.setattr(storage, "_run_publication_storage_process", run)

    storage.upload_publication_bytes("put-key", b"payload", "text/markdown")
    assert storage.download_publication_bytes("get-key") == b"payload"
    assert storage.list_publication_object_keys("research/run/") == [
        "research/run/generation/final.md"
    ]
    storage.delete_publication_object_if_exists("delete-key")

    assert [request.operation for request in requests] == [
        "put",
        "get",
        "list",
        "delete",
    ]
    assert requests[0].object_key == "put-key"
    assert requests[0].payload == b"payload"
    assert requests[0].content_type == "text/markdown"
    assert requests[1].object_key == "get-key"
    assert requests[2].prefix == "research/run/"
    assert requests[3].object_key == "delete-key"


@pytest.mark.parametrize(
    ("payload", "content_type", "error_type", "error_code"),
    [
        (
            bytearray(b"payload"),
            "text/markdown",
            TypeError,
            "publication_storage_payload_invalid",
        ),
        (
            b"x" * (storage.PUBLICATION_MAX_PAYLOAD_BYTES + 1),
            "text/markdown",
            ValueError,
            "publication_storage_payload_too_large",
        ),
        (
            b"payload",
            "application/octet-stream",
            ValueError,
            "publication_storage_content_type_invalid",
        ),
    ],
    ids=["wrong-payload-type", "oversize", "wrong-content-type"],
)
def test_publication_upload_rejects_invalid_input_before_spawning_child(
    monkeypatch,
    payload: object,
    content_type: str,
    error_type: type[Exception],
    error_code: str,
) -> None:
    calls: list[storage._PublicationStorageRequest] = []
    monkeypatch.setattr(
        storage,
        "_run_publication_storage_process",
        lambda request: calls.append(request),
    )

    with pytest.raises(error_type, match=f"^{error_code}$"):
        storage.upload_publication_bytes("research/run/final.md", payload, content_type)  # type: ignore[arg-type]

    assert calls == []


@pytest.mark.parametrize(
    ("adapter", "invalid_result"),
    [
        (lambda: storage.download_publication_bytes("key"), bytearray(b"payload")),
        (lambda: storage.list_publication_object_keys("prefix"), ("key",)),
        (lambda: storage.list_publication_object_keys("prefix"), [1]),
    ],
)
def test_publication_storage_adapters_reject_invalid_result_shapes(
    monkeypatch,
    adapter,
    invalid_result: object,
) -> None:
    monkeypatch.setattr(
        storage,
        "_run_publication_storage_process",
        lambda _request: invalid_result,
    )

    with pytest.raises(TypeError, match="^publication_storage_result_invalid$"):
        adapter()


def test_publication_client_disables_retries_and_sets_total_request_timeout(
    monkeypatch,
) -> None:
    pool_arguments: dict[str, object] = {}
    minio_arguments: dict[str, object] = {}
    http_client = object()

    def fake_pool_manager(**kwargs: object) -> object:
        pool_arguments.update(kwargs)
        return http_client

    def fake_minio(_endpoint: str, **kwargs: object) -> object:
        minio_arguments.update(kwargs)
        return object()

    monkeypatch.setattr(storage, "PoolManager", fake_pool_manager)
    monkeypatch.setattr(storage, "Minio", fake_minio)

    storage.build_publication_storage_client()

    timeout = pool_arguments["timeout"]
    assert timeout.total == storage.PUBLICATION_STORAGE_TIMEOUT_SECONDS
    assert timeout.connect_timeout == storage.PUBLICATION_STORAGE_TIMEOUT_SECONDS
    assert timeout.read_timeout == storage.PUBLICATION_STORAGE_TIMEOUT_SECONDS
    assert pool_arguments["retries"] is False
    assert minio_arguments["http_client"] is http_client
