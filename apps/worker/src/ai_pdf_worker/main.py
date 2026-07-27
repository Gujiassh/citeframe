from __future__ import annotations

import logging
import signal
from collections.abc import Callable
from threading import Event

from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.session import SessionLocal
from ai_pdf_api.modalities.image_caption import get_image_caption_provider
from ai_pdf_api.modalities.ingestion import IngestionAdapterRegistry
from ai_pdf_api.services.ingestion import (
    claim_next_ingestion_job,
    process_ingestion_job,
)
from ai_pdf_api.services.providers import get_embedding_provider

from ai_pdf_worker.image_ingestion import ImageIngestionAdapter
from ai_pdf_worker.metrics import WORKER_ACTIVE_JOBS, WORKER_JOBS, start_metrics_server
from ai_pdf_worker.pdf_ingestion import PdfIngestionAdapter

POLL_INTERVAL_SECONDS = 1.0
RETRY_INITIAL_DELAY_SECONDS = 1.0
RETRY_MAX_DELAY_SECONDS = 30.0
MAX_CONSECUTIVE_ERRORS = 5
INGESTION_ADAPTERS = IngestionAdapterRegistry(
    (
        PdfIngestionAdapter(),
        ImageIngestionAdapter(caption_provider=get_image_caption_provider()),
    )
)

logger = logging.getLogger("ai_pdf_worker")

ProcessJob = Callable[[], bool]
WaitForStop = Callable[[float], bool]


def process_one_job() -> bool:
    with SessionLocal() as db:
        job_id = claim_next_ingestion_job(db)
        if job_id is None:
            return False

        logger.info("worker_job_claimed job_id=%s", job_id)
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
        logger.info("worker_job_handled job_id=%s", job_id)
        return True


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
            logger.exception(
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
            logger.info("worker_error_recovered previous_errors=%s", consecutive_errors)
            consecutive_errors = 0

        if has_job:
            continue
        if wait_for_stop(poll_interval_seconds):
            logger.info("worker_stop_during_poll reason=shutdown_requested")
            break

    logger.info("worker_loop_stopped reason=stop_event")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    stop_event = Event()
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
    try:
        run_worker(stop_event=stop_event)
    except KeyboardInterrupt:
        logger.info("worker_stopped reason=keyboard_interrupt")
    except Exception as error:
        logger.exception("worker_fatal error_type=%s", type(error).__name__)
        raise
    else:
        logger.info("worker_stopped reason=stop_event")


if __name__ == "__main__":
    main()
