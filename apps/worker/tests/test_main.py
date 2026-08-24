import logging
import signal
import urllib.request
from collections.abc import Callable
from threading import Event

import ai_pdf_worker.main as worker
import pytest
from ai_pdf_worker.metrics import WORKER_JOBS


class SessionContext:
    def __init__(self, db: object) -> None:
        self.db = db

    def __enter__(self) -> object:
        return self.db

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None


def test_production_worker_enables_pdf_image_and_document_adapters() -> None:
    assert worker.INGESTION_ADAPTERS.asset_kinds == frozenset(
        {"pdf", "image", "document", "html", "docx", "xlsx", "pptx", "audio", "video"}
    )
    assert worker.INGESTION_ADAPTERS.get("document").asset_kind == "document"
    assert worker.INGESTION_ADAPTERS.get("docx").asset_kind == "docx"


def test_process_one_job_claims_and_handles_one_job(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db = object()
    calls: list[tuple[object, str, object]] = []
    provider = object()

    monkeypatch.setattr(worker, "SessionLocal", lambda: SessionContext(db))
    monkeypatch.setattr(worker, "claim_next_ingestion_job", lambda received_db: "job-1")
    monkeypatch.setattr(worker, "get_embedding_provider", lambda: provider)

    def fake_process(
        received_db: object,
        job_id: str,
        *,
        ingestion_adapters: object,
        embedding_provider: object,
    ) -> None:
        assert worker.WORKER_ACTIVE_JOBS._value.get() == 1
        assert ingestion_adapters is worker.INGESTION_ADAPTERS
        calls.append((received_db, job_id, embedding_provider))

    monkeypatch.setattr(worker, "process_ingestion_job", fake_process)

    claimed = WORKER_JOBS.labels(outcome="claimed")
    handled = WORKER_JOBS.labels(outcome="handled")
    before_claimed = claimed._value.get()
    before_handled = handled._value.get()
    with caplog.at_level(logging.INFO, logger=worker.logger.name):
        assert worker.process_one_job() is True
    assert calls == [(db, "job-1", provider)]
    assert "worker_job_claimed job_id=job-1" in caplog.text
    assert "worker_job_handled job_id=job-1" in caplog.text
    assert claimed._value.get() == before_claimed + 1
    assert handled._value.get() == before_handled + 1
    assert worker.WORKER_ACTIVE_JOBS._value.get() == 0


def test_process_one_job_returns_false_without_claiming_job(monkeypatch: pytest.MonkeyPatch) -> None:
    process_calls = 0

    class FakeSession:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
            return None

    monkeypatch.setattr(worker, "SessionLocal", FakeSession)
    monkeypatch.setattr(worker, "claim_next_ingestion_job", lambda _db: None)

    def fake_process(*_args: object, **_kwargs: object) -> None:
        nonlocal process_calls
        process_calls += 1

    monkeypatch.setattr(worker, "process_ingestion_job", fake_process)

    assert worker.process_one_job() is False
    assert process_calls == 0


def test_run_worker_retries_with_backoff_and_recovers(caplog: pytest.LogCaptureFixture) -> None:
    stop_event = Event()
    calls = 0
    delays: list[float] = []

    def process_job() -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary database outage")
        stop_event.set()
        return True

    def wait_for_stop(delay_seconds: float) -> bool:
        delays.append(delay_seconds)
        return False

    with caplog.at_level(logging.INFO, logger=worker.logger.name):
        worker.run_worker(
            stop_event=stop_event,
            process_job=process_job,
            wait_for_stop=wait_for_stop,
            retry_initial_delay_seconds=1.0,
            retry_max_delay_seconds=4.0,
            max_consecutive_errors=3,
        )

    assert calls == 2
    assert delays == [1.0]
    assert "worker_retry_scheduled" in caplog.text
    assert "worker_error_recovered previous_errors=1" in caplog.text
    assert "worker_loop_stopped" in caplog.text


def test_run_worker_stops_after_finite_retries(caplog: pytest.LogCaptureFixture) -> None:
    stop_event = Event()
    calls = 0
    delays: list[float] = []

    def process_job() -> bool:
        nonlocal calls
        calls += 1
        raise RuntimeError("persistent database outage")

    def wait_for_stop(delay_seconds: float) -> bool:
        delays.append(delay_seconds)
        return False

    with (caplog.at_level(logging.INFO, logger=worker.logger.name), pytest.raises(RuntimeError)):
        worker.run_worker(
            stop_event=stop_event,
            process_job=process_job,
            wait_for_stop=wait_for_stop,
            retry_initial_delay_seconds=1.0,
            retry_max_delay_seconds=2.0,
            max_consecutive_errors=3,
        )

    assert calls == 3
    assert delays == [1.0, 2.0]
    assert "worker_retry_exhausted attempts=3" in caplog.text


def test_install_signal_handlers_registers_sigint_and_sigterm(monkeypatch: pytest.MonkeyPatch) -> None:
    stop_event = Event()
    handlers: dict[int, Callable[[int, object], None]] = {}

    def fake_signal(signum: int, handler: Callable[[int, object], None]) -> None:
        handlers[signum] = handler

    monkeypatch.setattr(worker.signal, "signal", fake_signal)

    worker._install_signal_handlers(stop_event)

    assert set(handlers) == {signal.SIGINT, signal.SIGTERM}
    handlers[signal.SIGINT](signal.SIGINT, None)
    assert stop_event.is_set()


def test_shutdown_signal_sets_event_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    stop_event = Event()

    with caplog.at_level(logging.INFO, logger=worker.logger.name):
        worker._request_shutdown(stop_event, signal.SIGTERM)

    assert stop_event.is_set()
    assert "worker_shutdown_requested signal=SIGTERM" in caplog.text


def test_main_logs_fatal_process_error_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fake_install(_stop_event: Event) -> None:
        return None

    def fail_worker(**kwargs: object) -> None:
        if kwargs.get("process_job") is worker.process_one_ingestion_job:
            raise RuntimeError("fatal worker error")
        stop_event = kwargs["stop_event"]
        assert isinstance(stop_event, Event)
        stop_event.set()

    monkeypatch.setattr(worker, "_install_signal_handlers", fake_install)
    monkeypatch.setattr(worker, "run_worker", fail_worker)
    metrics_calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        worker,
        "start_metrics_server",
        lambda host, port: metrics_calls.append((host, port)),
    )

    with (
        caplog.at_level(logging.ERROR, logger=worker.logger.name),
        pytest.raises(RuntimeError, match="fatal worker error"),
    ):
        worker.main()

    assert "worker_fatal error_type=RuntimeError" in caplog.text
    assert metrics_calls == [(worker.settings.worker_metrics_host, worker.settings.worker_metrics_port)]


def test_main_preserves_ingestion_and_all_dispatcher_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Processor:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        def process_one(self) -> bool:
            return False

    def fail_worker(**kwargs: object) -> None:
        if kwargs.get("process_job") is worker.process_one_ingestion_job:
            raise ValueError("ingestion failed")
        raise RuntimeError("dispatcher failed")

    monkeypatch.setattr(worker, "ResearchWorkProcessor", Processor)
    monkeypatch.setattr(worker, "build_default_research_service", lambda: object())
    monkeypatch.setattr(worker, "run_worker", fail_worker)
    monkeypatch.setattr(worker, "start_metrics_server", lambda *_args: None)
    monkeypatch.setattr(worker, "_install_signal_handlers", lambda _event: None)

    with pytest.raises(BaseExceptionGroup, match="worker_loops_failed") as caught:
        worker.main()

    def leaves(error: BaseException) -> list[BaseException]:
        if isinstance(error, BaseExceptionGroup):
            return [leaf for child in error.exceptions for leaf in leaves(child)]
        cause = error.__cause__
        return [error, *leaves(cause)] if cause is not None else [error]

    messages = [str(error) for error in leaves(caught.value)]
    assert messages.count("dispatcher failed") == 2
    assert "ingestion failed" in messages


def test_process_one_job_propagates_handler_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    db = object()

    monkeypatch.setattr(worker, "SessionLocal", lambda: SessionContext(db))
    monkeypatch.setattr(worker, "claim_next_ingestion_job", lambda _db: "job-1")
    monkeypatch.setattr(worker, "get_embedding_provider", lambda: object())

    def fail_process(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("handler failure")

    monkeypatch.setattr(worker, "process_ingestion_job", fail_process)

    errors = WORKER_JOBS.labels(outcome="error")
    before_errors = errors._value.get()
    with pytest.raises(RuntimeError, match="handler failure"):
        worker.process_one_job()
    assert errors._value.get() == before_errors + 1
    assert worker.WORKER_ACTIVE_JOBS._value.get() == 0


def test_worker_metrics_server_exposes_prometheus_text() -> None:
    server, thread = worker.start_metrics_server("127.0.0.1", 0)
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_port}/metrics", timeout=2
        ) as response:
            body = response.read().decode()
        assert response.status == 200
        assert "ai_pdf_worker_jobs_total" in body
        assert "ai_pdf_worker_active_jobs" in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_retry_delay_is_exponential_and_bounded() -> None:
    assert [worker._retry_delay(attempt, 1.0, 3.0) for attempt in range(1, 5)] == [
        1.0,
        2.0,
        3.0,
        3.0,
    ]


def test_run_worker_stops_during_poll(caplog: pytest.LogCaptureFixture) -> None:
    stop_event = Event()
    process_calls = 0
    delays: list[float] = []

    def process_job() -> bool:
        nonlocal process_calls
        process_calls += 1
        return False

    def wait_for_stop(delay_seconds: float) -> bool:
        delays.append(delay_seconds)
        stop_event.set()
        return True

    with caplog.at_level(logging.INFO, logger=worker.logger.name):
        worker.run_worker(
            stop_event=stop_event,
            process_job=process_job,
            wait_for_stop=wait_for_stop,
            poll_interval_seconds=0.25,
        )

    assert process_calls == 1
    assert delays == [0.25]
    assert "worker_stop_during_poll reason=shutdown_requested" in caplog.text


def test_run_worker_stops_during_retry(caplog: pytest.LogCaptureFixture) -> None:
    stop_event = Event()
    process_calls = 0
    delays: list[float] = []

    def process_job() -> bool:
        nonlocal process_calls
        process_calls += 1
        raise RuntimeError("temporary database outage")

    def wait_for_stop(delay_seconds: float) -> bool:
        delays.append(delay_seconds)
        stop_event.set()
        return True

    with caplog.at_level(logging.INFO, logger=worker.logger.name):
        worker.run_worker(
            stop_event=stop_event,
            process_job=process_job,
            wait_for_stop=wait_for_stop,
            retry_initial_delay_seconds=1.0,
            retry_max_delay_seconds=4.0,
        )

    assert process_calls == 1
    assert delays == [1.0]
    assert "worker_stop_during_retry" in caplog.text


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_shutdown_signal_requests_stop_for_each_supported_signal(
    signum: signal.Signals,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop_event = Event()

    with caplog.at_level(logging.INFO, logger=worker.logger.name):
        worker._request_shutdown(stop_event, signum)

    assert stop_event.is_set()
    assert f"worker_shutdown_requested signal={signum.name}" in caplog.text
