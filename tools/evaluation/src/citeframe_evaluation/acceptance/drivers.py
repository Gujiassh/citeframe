"""Independent production consumers and bounded same-step recovery observation."""
from contextlib import contextmanager
from threading import Event
import time

from ai_pdf_worker.main import ResearchDispatcherPool
from ai_pdf_worker.research.runtime import ResearchWorkProcessor, build_default_research_service


@contextmanager
def consumers(session_factory):
    stop = Event()

    def factory(index):
        def sessions():
            return session_factory()
        return ResearchWorkProcessor(sessions, build_default_research_service(),
                                     worker_instance_id=f"acceptance-consumer-{index + 1}")

    pool = ResearchDispatcherPool(stop_event=stop, processor_factory=factory, width=2)
    pool.start()
    try:
        yield
    finally:
        pool.stop_and_join()
        pool.raise_if_failed()


def wait_for_reclaim(processor, observe, accepts, *, timeout_seconds=30):
    deadline = time.monotonic() + timeout_seconds
    observations = 0
    while True:
        evidence = observe()
        observations += 1
        if accepts(evidence) or time.monotonic() >= deadline:
            return evidence, observations
        # A global claim can legitimately execute a different ready step first.
        if not processor.process_one():
            time.sleep(min(0.05, max(0, deadline - time.monotonic())))
