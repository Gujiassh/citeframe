"""Synchronous admission remains independent of watchdog thread scheduling."""
from __future__ import annotations

import pytest
from ai_pdf_api.services import storage


class ChildExit(BaseException):
    pass


@pytest.fixture
def admission(monkeypatch):
    clock = [10.0]
    state = {"started": 0, "allocated": 0, "joined": 0, "calls": 0}
    threads = []

    def exit_child(code):
        assert code == storage.PUBLICATION_STORAGE_WATCHDOG_EXIT_CODE == 124
        raise ChildExit

    class DeferredWatchdog:
        def __init__(self, *, target, kwargs, name, daemon):
            assert target is storage._publication_storage_watchdog
            assert name == "publication-storage-watchdog" and daemon
            self.stop = kwargs["stop"]
            state["allocated"] += 1
            threads.append(self)

        def start(self):
            state["started"] += 1
            clock[0] = state.get("after_start", clock[0])

        def join(self, *, timeout):
            assert timeout == storage.PUBLICATION_STORAGE_WATCHDOG_POLL_SECONDS * 2
            assert self.stop.is_set()
            state["joined"] += 1

    def operation(connection, request):
        assert (connection, request) == ("local-pipe", "no-storage-request")
        state["calls"] += 1
        if state.get("raise_operation"):
            raise ValueError("fixture operation failure")

    monkeypatch.setattr(storage.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(storage.os, "_exit", exit_child)
    monkeypatch.setattr(storage.threading, "Thread", DeferredWatchdog)

    def enter(deadline):
        storage._publication_storage_child_entry(
            "local-pipe", "no-storage-request", deadline, 123, operation
        )

    return state, enter


@pytest.mark.parametrize("deadline", [9.0, 10.0])
def test_expired_child_does_not_allocate_watchdog_or_enter_operation(admission, deadline):
    state, enter = admission
    with pytest.raises(ChildExit):
        enter(deadline)
    assert state["allocated"] == state["started"] == state["calls"] == 0


@pytest.mark.parametrize("after_start", [11.0, 12.0])
def test_deadline_crossed_during_watchdog_start_blocks_operation(admission, after_start):
    state, enter = admission
    state["after_start"] = after_start
    with pytest.raises(ChildExit):
        enter(11.0)
    assert state["started"] == 1
    assert state["calls"] == 0


def test_live_deadline_runs_operation_once_and_stops_watchdog(admission):
    state, enter = admission
    state["after_start"] = 10.5
    enter(11.0)
    assert state["calls"] == state["started"] == state["joined"] == 1


def test_operation_failure_keeps_existing_watchdog_cleanup(admission):
    state, enter = admission
    state["raise_operation"] = True
    with pytest.raises(ValueError, match="fixture operation failure"):
        enter(11.0)
    assert state["calls"] == state["started"] == state["joined"] == 1

# The subprocess cases observe the production entrypoint without replacing os._exit.
def _record_operation_entry(connection, _request):
    connection.send("operation-entered")
    storage.time.sleep(1)


def _run_scheduled_admission_probe(connection, phase):
    import os
    import time

    original_thread = storage.threading.Thread

    class ScheduledWatchdog(original_thread):
        def run(self):
            time.sleep(0.05)
            super().run()

        def start(self):
            if phase == "during_start":
                time.sleep(0.02)
            super().start()

    storage.threading.Thread = ScheduledWatchdog
    deadline = time.monotonic() + (0.01 if phase == "during_start" else -1)
    storage._publication_storage_child_entry(
        connection, None, deadline, os.getppid(), _record_operation_entry
    )


@pytest.mark.parametrize("phase", ["already_expired", "during_start"])
def test_spawned_expired_child_never_enters_operation(phase):
    import multiprocessing

    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_run_scheduled_admission_probe, args=(sender, phase))
    entered = False
    try:
        process.start()
        sender.close()
        process.join(timeout=5)
        assert not process.is_alive()
        assert process.exitcode == storage.PUBLICATION_STORAGE_WATCHDOG_EXIT_CODE == 124
        try:
            entered = receiver.poll() and receiver.recv() == "operation-entered"
        except (EOFError, BrokenPipeError):
            pass
        assert not entered
    finally:
        receiver.close()
        sender.close()
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)
