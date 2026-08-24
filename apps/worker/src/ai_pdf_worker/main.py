from __future__ import annotations

import logging
import os
import signal
from collections.abc import Callable
from threading import Event, Lock, Thread
from time import monotonic

from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.session import SessionLocal
from ai_pdf_api.modalities.ingestion import IngestionAdapterRegistry
from ai_pdf_api.services.ingestion import (
    claim_next_ingestion_job,
    process_ingestion_job,
)
from ai_pdf_api.services.providers import get_embedding_provider
from ai_pdf_api.core.research_observability import (
    configure_research_observability,
    observe_research_recovery,
    research_log,
)

from ai_pdf_worker.audio_ingestion import AudioIngestionAdapter
from ai_pdf_worker.video_ingestion import VideoIngestionAdapter
from ai_pdf_worker.document_ingestion import DocumentIngestionAdapter
from ai_pdf_worker.html_ingestion import HtmlIngestionAdapter
from ai_pdf_worker.docx_ingestion import DocxIngestionAdapter
from ai_pdf_worker.image_ingestion import ImageIngestionAdapter
from ai_pdf_worker.metrics import WORKER_ACTIVE_JOBS, WORKER_JOBS, start_metrics_server
from ai_pdf_worker.pdf_ingestion import PdfIngestionAdapter
from ai_pdf_worker.pptx_ingestion import PptxIngestionAdapter
from ai_pdf_worker.xlsx_ingestion import XlsxIngestionAdapter
from ai_pdf_worker.research_runtime import ResearchWorkProcessor, build_default_research_service

POLL_INTERVAL_SECONDS = 1.0
RETRY_INITIAL_DELAY_SECONDS = 1.0
RETRY_MAX_DELAY_SECONDS = 30.0
MAX_CONSECUTIVE_ERRORS = 5
RESEARCH_DISPATCHER_LOOPS = 2
RESEARCH_POOL_SHUTDOWN_TIMEOUT_SECONDS = 130.0
INGESTION_ADAPTERS = IngestionAdapterRegistry(
    (
        PdfIngestionAdapter(),
        ImageIngestionAdapter(),  # caption provider resolved at first image ingest
        DocumentIngestionAdapter(),
        HtmlIngestionAdapter(),
        DocxIngestionAdapter(),
        # Office/html/audio/video adapters are production-enabled at S0.
        XlsxIngestionAdapter(),
        PptxIngestionAdapter(),
        AudioIngestionAdapter(),
        VideoIngestionAdapter(),
    )
)

logger = logging.getLogger("ai_pdf_worker")

ProcessJob = Callable[[], bool]
WaitForStop = Callable[[float], bool]
ResearchProcessorFactory = Callable[[], ResearchWorkProcessor]
IndexedResearchProcessorFactory = Callable[[int], ResearchWorkProcessor]

# Tests and ingestion-only deployments leave this unset.  ``main`` enables it
# explicitly, so importing the worker never makes Research a hidden dependency.
RESEARCH_PROCESSOR_FACTORY: ResearchProcessorFactory | None = None
_PREFER_RESEARCH = False


def _process_ingestion_job(db: object) -> bool:
    job_id = claim_next_ingestion_job(db)
    if job_id is None:
        return False

    logger.info("worker_job_claimed job_id=%s lane=ingestion", job_id)
    WORKER_JOBS.labels(outcome="claimed").inc()
    WORKER_ACTIVE_JOBS.inc()
    try:
        process_ingestion_job(
            db,
            job_id,
            ingestion_adapters=INGESTION_ADAPTERS,
            embedding_provider=get_embedding_provider(),
        )
    except Exception:
        WORKER_JOBS.labels(outcome="error").inc()
        raise
    finally:
        WORKER_ACTIVE_JOBS.dec()
    WORKER_JOBS.labels(outcome="handled").inc()
    logger.info("worker_job_handled job_id=%s lane=ingestion", job_id)
    return True


def _process_research_job() -> bool:
    if RESEARCH_PROCESSOR_FACTORY is None:
        return False
    return _process_research_processor_job(RESEARCH_PROCESSOR_FACTORY())


def _process_research_processor_job(processor: ResearchWorkProcessor) -> bool:
    WORKER_ACTIVE_JOBS.inc()
    try:
        if not processor.process_one():
            return False
    except Exception:
        WORKER_JOBS.labels(outcome="error").inc()
        raise
    finally:
        WORKER_ACTIVE_JOBS.dec()
    WORKER_JOBS.labels(outcome="research_claimed").inc()
    WORKER_JOBS.labels(outcome="research_handled").inc()
    return True


def process_one_ingestion_job() -> bool:
    with SessionLocal() as db:
        return _process_ingestion_job(db)


def process_one_job() -> bool:
    global _PREFER_RESEARCH
    lanes = ("research", "ingestion") if _PREFER_RESEARCH else ("ingestion", "research")
    for lane in lanes:
        if lane == "research":
            handled = _process_research_job()
        else:
            handled = process_one_ingestion_job()
        if handled:
            _PREFER_RESEARCH = lane == "ingestion"
            return True
    return False


def _retry_delay(
    consecutive_errors: int,
    initial_delay_seconds: float,
    max_delay_seconds: float,
) -> float:
    return min(
        max_delay_seconds,
        initial_delay_seconds * (2 ** (consecutive_errors - 1)),
    )


def _request_shutdown(stop_event: Event, signum: int) -> None:
    try:
        signal_name = signal.Signals(signum).name
    except ValueError:
        signal_name = str(signum)
    logger.info("worker_shutdown_requested signal=%s", signal_name)
    stop_event.set()


def _install_signal_handlers(stop_event: Event) -> None:
    def handle_signal(signum: int, _frame: object) -> None:
        _request_shutdown(stop_event, signum)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)


def run_worker(
    *,
    stop_event: Event | None = None,
    process_job: ProcessJob | None = None,
    wait_for_stop: WaitForStop | None = None,
    poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
    retry_initial_delay_seconds: float = RETRY_INITIAL_DELAY_SECONDS,
    retry_max_delay_seconds: float = RETRY_MAX_DELAY_SECONDS,
    max_consecutive_errors: int = MAX_CONSECUTIVE_ERRORS,
) -> None:
    if max_consecutive_errors < 1:
        raise ValueError("max_consecutive_errors must be at least 1")
    if poll_interval_seconds < 0:
        raise ValueError("poll_interval_seconds must be non-negative")
    if retry_initial_delay_seconds < 0 or retry_max_delay_seconds < 0:
        raise ValueError("retry delays must be non-negative")
    if retry_max_delay_seconds < retry_initial_delay_seconds:
        raise ValueError("retry_max_delay_seconds must be >= retry_initial_delay_seconds")

    if stop_event is None:
        stop_event = Event()
    if process_job is None:
        process_job = process_one_job
    if wait_for_stop is None:
        wait_for_stop = stop_event.wait

    consecutive_errors = 0
    while not stop_event.is_set():
        try:
            has_job = process_job()
        except Exception as error:
            consecutive_errors += 1
            logger.error(
                "worker_iteration_failed attempt=%s max_consecutive_errors=%s error_type=%s",
                consecutive_errors,
                max_consecutive_errors,
                type(error).__name__,
            )
            if stop_event.is_set():
                logger.info("worker_stop_after_iteration_error reason=shutdown_requested")
                break
            if consecutive_errors >= max_consecutive_errors:
                logger.critical(
                    "worker_retry_exhausted attempts=%s error_type=%s",
                    consecutive_errors,
                    type(error).__name__,
                )
                raise

            observe_research_recovery("retry")
            research_log(
                logger,
                tag="research_retry",
                status="retry",
                level=logging.WARNING,
                fields={"attempt_number": consecutive_errors, "reason_code": type(error).__name__},
            )

            delay_seconds = _retry_delay(
                consecutive_errors,
                retry_initial_delay_seconds,
                retry_max_delay_seconds,
            )
            logger.warning(
                "worker_retry_scheduled attempt=%s delay_seconds=%.3f error_type=%s",
                consecutive_errors,
                delay_seconds,
                type(error).__name__,
            )
            if wait_for_stop(delay_seconds):
                logger.info("worker_stop_during_retry")
                break
            continue

        if consecutive_errors:
            observe_research_recovery("recovered")
            research_log(
                logger,
                tag="research_recovery",
                status="recovered",
                fields={"attempt_number": consecutive_errors},
            )
            logger.info("worker_error_recovered previous_errors=%s", consecutive_errors)
            consecutive_errors = 0

        if has_job:
            continue
        if wait_for_stop(poll_interval_seconds):
            logger.info("worker_stop_during_poll reason=shutdown_requested")
            break

    logger.info("worker_loop_stopped reason=stop_event")


class ResearchDispatcherPool:
    """Bounded production pool with one processor per long-lived loop."""

    def __init__(
        self,
        *,
        stop_event: Event,
        processor_factory: IndexedResearchProcessorFactory,
        width: int,
    ) -> None:
        if width < 2:
            raise ValueError("Research dispatcher pool requires at least two loops")
        self._stop_event = stop_event
        self._processor_factory = processor_factory
        self._width = width
        self._threads: list[Thread] = []
        self._errors: list[BaseException] = []
        self._error_lock = Lock()

    def start(self) -> None:
        if self._threads:
            raise RuntimeError("Research dispatcher pool already started")
        for loop_index in range(self._width):
            thread = Thread(
                target=self._run_loop,
                args=(loop_index,),
                name=f"research-dispatcher-{loop_index + 1}",
                daemon=False,
            )
            self._threads.append(thread)
            thread.start()

    def _run_loop(self, loop_index: int) -> None:
        try:
            processor = self._processor_factory(loop_index)
            run_worker(
                stop_event=self._stop_event,
                process_job=lambda: _process_research_processor_job(processor),
            )
        except BaseException as error:  # noqa: BLE001 - the controller must stop sibling loops
            with self._error_lock:
                self._errors.append(error)
            self._stop_event.set()

    def stop_and_join(
        self,
        *,
        timeout_seconds: float = RESEARCH_POOL_SHUTDOWN_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative")
        self._stop_event.set()
        deadline = monotonic() + timeout_seconds
        for thread in self._threads:
            thread.join(timeout=max(0.0, deadline - monotonic()))
        alive = [thread.name for thread in self._threads if thread.is_alive()]
        if alive:
            raise RuntimeError(f"research_dispatcher_shutdown_timeout:{','.join(alive)}")

    def raise_if_failed(self) -> None:
        with self._error_lock:
            errors = tuple(self._errors)
        if len(errors) == 1:
            raise RuntimeError("research_dispatcher_loop_failed") from errors[0]
        if errors:
            raise BaseExceptionGroup("research_dispatcher_loops_failed", list(errors))


def _research_dispatcher_width() -> int:
    raw = os.environ.get("AI_PDF_RESEARCH_DISPATCHER_LOOPS")
    width = RESEARCH_DISPATCHER_LOOPS if raw is None else int(raw)
    if width < 2:
        raise ValueError("AI_PDF_RESEARCH_DISPATCHER_LOOPS must be at least 2")
    return width


def _loop_session_factory() -> Callable[[], object]:
    """Give each dispatcher loop a distinct SQLAlchemy session-factory identity."""

    def open_session() -> object:
        return SessionLocal()

    return open_session


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    stop_event = Event()
    configure_research_observability(
        service_name=settings.research_otel_service_name,
        endpoint=settings.research_otel_endpoint,
        export_timeout_seconds=settings.research_otel_export_timeout_seconds,
    )
    base_worker_id = os.environ.get("AI_PDF_WORKER_INSTANCE_ID") or f"worker-{os.getpid()}"
    research_pool = ResearchDispatcherPool(
        stop_event=stop_event,
        width=_research_dispatcher_width(),
        processor_factory=lambda loop_index: ResearchWorkProcessor(
            _loop_session_factory(),
            build_default_research_service(),
            worker_instance_id=f"{base_worker_id}:research:{loop_index + 1}",
        ),
    )
    start_metrics_server(settings.worker_metrics_host, settings.worker_metrics_port)
    _install_signal_handlers(stop_event)
    logger.info(
        "worker_start poll_interval_seconds=%.3f max_consecutive_errors=%s "
        "retry_initial_delay_seconds=%.3f retry_max_delay_seconds=%.3f",
        POLL_INTERVAL_SECONDS,
        MAX_CONSECUTIVE_ERRORS,
        RETRY_INITIAL_DELAY_SECONDS,
        RETRY_MAX_DELAY_SECONDS,
    )
    primary_error: Exception | None = None
    shutdown_error: Exception | None = None
    try:
        research_pool.start()
        try:
            run_worker(stop_event=stop_event, process_job=process_one_ingestion_job)
        except KeyboardInterrupt:
            logger.info("worker_stopped reason=keyboard_interrupt")
        except Exception as error:
            logger.error("worker_fatal error_type=%s", type(error).__name__)
            primary_error = error
        else:
            logger.info("worker_stopped reason=stop_event")
    finally:
        try:
            research_pool.stop_and_join()
        except Exception as error:
            shutdown_error = error
    pool_error: BaseException | None = None
    try:
        research_pool.raise_if_failed()
    except BaseException as error:  # noqa: BLE001 - preserve every dispatcher failure
        pool_error = error
    failures = [
        error
        for error in (primary_error, shutdown_error, pool_error)
        if error is not None
    ]
    if len(failures) > 1:
        raise BaseExceptionGroup("worker_loops_failed", failures)
    if failures:
        raise failures[0]


if __name__ == "__main__":
    main()
