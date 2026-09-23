from __future__ import annotations

import multiprocessing
import os
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from io import BytesIO
from typing import Any, BinaryIO, Literal

from ai_pdf_api.core.metrics import observe_storage_operation
from ai_pdf_api.core.settings import settings
from minio import Minio
from minio.error import S3Error
from urllib3 import PoolManager, Timeout

PUBLICATION_STORAGE_TIMEOUT_SECONDS = 15.0
PUBLICATION_MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
PUBLICATION_UPLOAD_PART_SIZE_BYTES = PUBLICATION_MAX_PAYLOAD_BYTES
PUBLICATION_STORAGE_HARD_DEADLINE_SECONDS = 20.0
PUBLICATION_STORAGE_TERMINATE_GRACE_SECONDS = 2.0
PUBLICATION_STORAGE_KILL_GRACE_SECONDS = 2.0
PUBLICATION_STORAGE_WATCHDOG_POLL_SECONDS = 0.1
PUBLICATION_STORAGE_WATCHDOG_EXIT_CODE = 124
PUBLICATION_STORAGE_MAX_LOGICAL_SECONDS = (
    PUBLICATION_STORAGE_HARD_DEADLINE_SECONDS
    + PUBLICATION_STORAGE_TERMINATE_GRACE_SECONDS
    + PUBLICATION_STORAGE_KILL_GRACE_SECONDS
)
# Keep a separate reconciliation margin beyond the worst-case process teardown.
PUBLICATION_ORPHAN_OBSERVATION_SECONDS = 30.0


@dataclass(frozen=True)
class _PublicationStorageRequest:
    operation: Literal["put", "get", "list", "delete"]
    endpoint: str
    access_key: str
    secret_key: str
    secure: bool
    bucket: str
    object_key: str = ""
    prefix: str = ""
    payload: bytes = b""
    content_type: str = "application/octet-stream"


def _publication_request(
    operation: Literal["put", "get", "list", "delete"],
    *,
    object_key: str = "",
    prefix: str = "",
    payload: bytes = b"",
    content_type: str = "application/octet-stream",
) -> _PublicationStorageRequest:
    return _PublicationStorageRequest(
        operation=operation,
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
        bucket=settings.minio_bucket,
        object_key=object_key,
        prefix=prefix,
        payload=payload,
        content_type=content_type,
    )


def _publication_client_for_request(request: _PublicationStorageRequest) -> Minio:
    return Minio(
        request.endpoint,
        access_key=request.access_key,
        secret_key=request.secret_key,
        secure=request.secure,
        http_client=PoolManager(
            timeout=Timeout(
                connect=PUBLICATION_STORAGE_TIMEOUT_SECONDS,
                read=PUBLICATION_STORAGE_TIMEOUT_SECONDS,
                total=PUBLICATION_STORAGE_TIMEOUT_SECONDS,
            ),
            retries=False,
            cert_reqs="CERT_REQUIRED",
        ),
    )


def _publication_storage_child(connection: Any, request: _PublicationStorageRequest) -> None:
    """Spawn target: execute one request and return only data or a safe error type."""

    try:
        client = _publication_client_for_request(request)
        if request.operation == "put":
            if not client.bucket_exists(request.bucket):
                client.make_bucket(request.bucket)
            client.put_object(
                request.bucket,
                request.object_key,
                BytesIO(request.payload),
                length=len(request.payload),
                content_type=request.content_type,
                part_size=PUBLICATION_UPLOAD_PART_SIZE_BYTES,
            )
            result: object = None
        elif request.operation == "get":
            response = client.get_object(request.bucket, request.object_key)
            try:
                result = response.read(PUBLICATION_MAX_PAYLOAD_BYTES + 1)
                if len(result) > PUBLICATION_MAX_PAYLOAD_BYTES:
                    raise ValueError("publication_storage_payload_too_large")
            finally:
                response.close()
                response.release_conn()
        elif request.operation == "list":
            try:
                result = [
                    item.object_name
                    for item in client.list_objects(
                        request.bucket,
                        prefix=request.prefix,
                        recursive=True,
                    )
                    if item.object_name
                ]
            except S3Error as error:
                if error.code not in {"NoSuchBucket", "NoSuchKey", "NoSuchObject"}:
                    raise
                result = []
        else:
            try:
                client.remove_object(request.bucket, request.object_key)
            except S3Error as error:
                if error.code not in {"NoSuchBucket", "NoSuchKey", "NoSuchObject"}:
                    raise
            result = None
        connection.send(("ok", result))
    except Exception as error:  # noqa: BLE001 - child must sanitize every SDK failure
        # Never cross the process boundary with exception messages: SDK/network
        # messages can contain endpoints or credentials.
        try:
            connection.send(("error", type(error).__name__))
        except (BrokenPipeError, EOFError, OSError):
            return
    finally:
        connection.close()


def _publication_storage_watchdog(
    stop: threading.Event,
    *,
    deadline_at: float,
    parent_pid: int,
) -> None:
    """Kill this child if its supervisor dies or its own deadline expires."""

    parent = multiprocessing.parent_process()
    while not stop.is_set():
        remaining = deadline_at - time.monotonic()
        if remaining <= 0:
            os._exit(PUBLICATION_STORAGE_WATCHDOG_EXIT_CODE)
        if (
            parent is None
            or parent.pid != parent_pid
            or not parent.is_alive()
        ):
            os._exit(PUBLICATION_STORAGE_WATCHDOG_EXIT_CODE)
        stop.wait(min(PUBLICATION_STORAGE_WATCHDOG_POLL_SECONDS, remaining))


def _publication_storage_child_entry(
    connection: Any,
    request: _PublicationStorageRequest,
    deadline_at: float,
    parent_pid: int,
    operation_target: Any,
) -> None:
    """Run one operation under a watchdog independent of the parent Worker."""

    stop = threading.Event()
    watchdog = threading.Thread(
        target=_publication_storage_watchdog,
        kwargs={
            "stop": stop,
            "deadline_at": deadline_at,
            "parent_pid": parent_pid,
        },
        name="publication-storage-watchdog",
        daemon=True,
    )
    watchdog.start()
    try:
        operation_target(connection, request)
    finally:
        stop.set()
        watchdog.join(timeout=PUBLICATION_STORAGE_WATCHDOG_POLL_SECONDS * 2)


def _stop_publication_storage_process(process: Any) -> None:
    """Stop a child deterministically or fail instead of leaking it."""

    if not process.is_alive():
        process.join(timeout=0)
        return
    process.terminate()
    process.join(timeout=PUBLICATION_STORAGE_TERMINATE_GRACE_SECONDS)
    if process.is_alive():
        process.kill()
        process.join(timeout=PUBLICATION_STORAGE_KILL_GRACE_SECONDS)
    if process.is_alive():
        raise RuntimeError("publication_storage_process_cleanup_failed")


def _run_publication_storage_process(
    request: _PublicationStorageRequest,
    *,
    deadline_seconds: float = PUBLICATION_STORAGE_HARD_DEADLINE_SECONDS,
    process_target: Any = _publication_storage_child,
) -> object:
    if deadline_seconds <= 0:
        raise ValueError("publication storage deadline must be positive")
    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=False)
    deadline_at = time.monotonic() + deadline_seconds
    process = context.Process(
        target=_publication_storage_child_entry,
        args=(
            child_connection,
            request,
            deadline_at,
            os.getpid(),
            process_target,
        ),
        name=f"publication-storage-{request.operation}",
        daemon=True,
    )
    try:
        process.start()
        child_connection.close()
        remaining = max(0.0, deadline_at - time.monotonic())
        if not parent_connection.poll(remaining):
            _stop_publication_storage_process(process)
            raise TimeoutError("publication_storage_hard_timeout")
        try:
            response = parent_connection.recv()
        except EOFError as error:
            _stop_publication_storage_process(process)
            if time.monotonic() >= deadline_at:
                raise TimeoutError("publication_storage_hard_timeout") from error
            raise RuntimeError("publication_storage_child_no_result") from error
        _stop_publication_storage_process(process)
        if not isinstance(response, tuple) or len(response) != 2:
            raise RuntimeError("publication_storage_response_invalid")
        status, result = response
        if status != "ok":
            error_type = (
                result
                if isinstance(result, str) and result.isidentifier()
                else "UnknownError"
            )
            raise RuntimeError(f"publication_storage_failed:{error_type}")
        return result
    finally:
        parent_connection.close()
        child_connection.close()


def build_storage_client() -> Minio:
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def build_publication_storage_client() -> Minio:
    """Build the non-retrying client used inside publication child processes."""

    return _publication_client_for_request(
        _publication_request("list")
    )


def ensure_bucket_exists(client: Minio) -> None:
    with observe_storage_operation("ensure_bucket"):
        if not client.bucket_exists(settings.minio_bucket):
            client.make_bucket(settings.minio_bucket)


def upload_bytes(object_key: str, payload: bytes, content_type: str) -> None:
    upload_stream(object_key, BytesIO(payload), len(payload), content_type)


def upload_stream(object_key: str, payload: BinaryIO, length: int, content_type: str) -> None:
    client = build_storage_client()
    ensure_bucket_exists(client)
    with observe_storage_operation("upload"):
        client.put_object(
            settings.minio_bucket,
            object_key,
            payload,
            length=length,
            content_type=content_type,
        )


def object_exists(object_key: str) -> bool:
    client = build_storage_client()
    with observe_storage_operation("stat"):
        try:
            client.stat_object(settings.minio_bucket, object_key)
            return True
        except S3Error as error:
            if error.code in {"NoSuchBucket", "NoSuchKey", "NoSuchObject"}:
                return False
            raise


def download_bytes(object_key: str) -> bytes:
    client = build_storage_client()
    with observe_storage_operation("download"):
        response = client.get_object(settings.minio_bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()


def stream_bytes(object_key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    client = build_storage_client()
    with observe_storage_operation("stream"):
        response = client.get_object(settings.minio_bucket, object_key)
        try:
            while chunk := response.read(chunk_size):
                yield chunk
        finally:
            response.close()
            response.release_conn()


def delete_object_if_exists(object_key: str) -> None:
    client = build_storage_client()
    with observe_storage_operation("delete"):
        try:
            client.remove_object(settings.minio_bucket, object_key)
        except S3Error as error:
            if error.code in {"NoSuchBucket", "NoSuchKey", "NoSuchObject"}:
                return
            raise


def delete_objects_with_prefix(prefix: str) -> None:
    client = build_storage_client()
    try:
        with observe_storage_operation("list"):
            object_keys = [
                item.object_name
                for item in client.list_objects(
                    settings.minio_bucket,
                    prefix=prefix,
                    recursive=True,
                )
                if item.object_name
            ]
    except S3Error as error:
        if error.code in {"NoSuchBucket", "NoSuchKey", "NoSuchObject"}:
            return
        raise

    for object_key in object_keys:
        with observe_storage_operation("delete"):
            client.remove_object(settings.minio_bucket, object_key)


def upload_publication_bytes(object_key: str, payload: bytes, content_type: str) -> None:
    if type(payload) is not bytes:
        raise TypeError("publication_storage_payload_invalid")
    if len(payload) > PUBLICATION_MAX_PAYLOAD_BYTES:
        raise ValueError("publication_storage_payload_too_large")
    if content_type != "text/markdown":
        raise ValueError("publication_storage_content_type_invalid")
    with observe_storage_operation("publication_upload"):
        _run_publication_storage_process(
            _publication_request(
                "put",
                object_key=object_key,
                payload=payload,
                content_type=content_type,
            )
        )


def download_publication_bytes(object_key: str) -> bytes:
    with observe_storage_operation("publication_download"):
        result = _run_publication_storage_process(
            _publication_request("get", object_key=object_key)
        )
    if not isinstance(result, bytes):
        raise TypeError("publication_storage_result_invalid")
    return result


def list_publication_object_keys(prefix: str) -> list[str]:
    with observe_storage_operation("publication_list"):
        result = _run_publication_storage_process(
            _publication_request("list", prefix=prefix)
        )
    if not isinstance(result, list) or any(not isinstance(key, str) for key in result):
        raise TypeError("publication_storage_result_invalid")
    return result


def delete_publication_object_if_exists(object_key: str) -> None:
    with observe_storage_operation("publication_delete"):
        _run_publication_storage_process(
            _publication_request("delete", object_key=object_key)
        )
