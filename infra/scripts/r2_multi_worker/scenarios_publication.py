"""Real-PostgreSQL final-publication commit-outcome evidence for R2."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from citeframe_persistence.models import (
    ResearchArtifact,
    ResearchArtifactPromptVersion,
    ResearchEvent,
    ResearchExecutionPromptVersion,
    ResearchExecutionSnapshot,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
)
from citeframe_research_persistence.errors import ResearchError
from citeframe_research_persistence.lease import claim_specific_research_step
from citeframe_research_persistence.publication import (
    _final_commit_state,
    publish_final_report,
)
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from .common import error_json, utcnow

_PUBLICATION_SOURCE = (
    "packages/research-persistence/src/citeframe_research_persistence/publication.py"
)
_SCENARIO_SOURCE = "infra/scripts/r2_multi_worker/scenarios_publication.py"
_TERMINAL_EVENT_TYPES = ("step_succeeded", "artifact_published", "run_completed")


class _CommitAcknowledgementLost(RuntimeError):
    """The database committed, but the caller did not receive the acknowledgement."""


class _PrecommitRejected(RuntimeError):
    """The SQLAlchemy Session rejected the transaction before DBAPI commit."""


class _ObjectStoreProbe:
    """Filesystem-backed object probe that fails on duplicate stores or cleanup."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=False)
        self.store_calls: list[dict[str, Any]] = []
        self.cleanup_calls: list[str] = []

    @staticmethod
    def _artifact_id(object_key: str) -> str:
        parts = object_key.split("/")
        if len(parts) != 5 or parts[0] != "research" or parts[-1] != "final.md":
            raise AssertionError(f"unexpected final-report object key: {object_key}")
        return parts[-2]

    def _path(self, object_key: str) -> Path:
        return self.root / hashlib.sha256(object_key.encode("utf-8")).hexdigest()

    def store(self, object_key: str, content: bytes, content_type: str) -> None:
        target = self._path(object_key)
        if target.exists():
            raise AssertionError(f"duplicate object store: {object_key}")
        target.write_bytes(content)
        self.store_calls.append(
            {
                "artifactId": self._artifact_id(object_key),
                "objectKey": object_key,
                "contentType": content_type,
                "byteSize": len(content),
                "contentSha256": hashlib.sha256(content).hexdigest(),
            }
        )

    def cleanup(self, object_key: str) -> None:
        target = self._path(object_key)
        if not target.exists():
            raise AssertionError(f"duplicate or absent object cleanup: {object_key}")
        target.unlink()
        self.cleanup_calls.append(object_key)

    @property
    def publication(self) -> dict[str, Any]:
        if len(self.store_calls) != 1:
            raise AssertionError(
                f"expected one publication object, observed {len(self.store_calls)}"
            )
        return self.store_calls[0]

    def evidence(self) -> dict[str, Any]:
        retained = [
            row["objectKey"]
            for row in self.store_calls
            if self._path(row["objectKey"]).exists()
        ]
        return {
            "storeCalls": list(self.store_calls),
            "cleanupCalls": list(self.cleanup_calls),
            "retainedObjectKeys": retained,
            "retainedObjectCount": len(retained),
        }


class PublicationOutcomeScenarios:
    """Mixin proving publication commit outcomes against the harness PostgreSQL."""

    def scenario_publication_outcome_matrix(self) -> dict[str, Any]:
        binding_before = self._publication_evidence_binding()
        cases = [
            self._case_committed_ack_loss(),
            self._case_absent_precommit_fault(),
            self._case_unknown_committed(),
            self._case_unknown_absent_manual_compensation(),
        ]
        binding_after = self._publication_evidence_binding()
        source_stable = binding_before == binding_after
        passed = source_stable and all(case["status"] == "pass" for case in cases)
        return {
            "status": "pass" if passed else "fail",
            "sourceAndHarnessSnapshotStable": source_stable,
            "sourceAndHarnessSnapshot": binding_after,
            "classificationBoundary": {
                "productionAutomatic": (
                    "committed/absent classification performed inside publish_final_report only "
                    "when its committed_session_factory is available"
                ),
                "harnessManual": (
                    "unknown cases are classified later by an explicit harness call to "
                    "_final_commit_state; only the unknown-absent case is then compensated "
                    "explicitly by the harness"
                ),
                "productionReconcileClaimed": False,
            },
            "cases": cases,
        }

    def _case_committed_ack_loss(self) -> dict[str, Any]:
        fixture, lease, before = self._prepare_publication_case(
            "r2-publication-committed-ack-loss"
        )
        storage = _ObjectStoreProbe(self.temp_path / "publication-committed-ack-loss")
        fault: dict[str, Any]
        returned_artifact_id: str | None = None
        caught: BaseException | None = None
        with self.sessions() as db, self._commit_ack_loss(db) as fault:
            try:
                returned_artifact_id = self._publish(
                    db,
                    lease=lease,
                    storage=storage,
                    committed_session_factory=self.sessions,
                )
            except BaseException as error:  # noqa: BLE001 - evidence records exact outcome
                caught = error
        facts = self._publication_facts(fixture.run_id, lease.attempt_id)
        manual_state = self._manual_final_commit_state(
            fixture=fixture,
            lease=lease,
            storage=storage,
        )
        duplicate_free = self._committed_terminal_facts_are_unique(facts)
        passed = (
            caught is None
            and fault["fired"] == 1
            and returned_artifact_id == storage.publication["artifactId"]
            and storage.evidence()["retainedObjectCount"] == 1
            and storage.evidence()["cleanupCalls"] == []
            and manual_state == "committed"
            and duplicate_free
        )
        return {
            "name": "committed-ack-loss-classified-committed-returned",
            "status": "pass" if passed else "fail",
            "fault": fault,
            "callerOutcome": (
                {"kind": "returned", "artifactId": returned_artifact_id}
                if caught is None
                else {"kind": "raised", "error": error_json(caught)}
            ),
            "productionClassificationEvidence": {
                "state": "committed"
                if caught is None and fault["fired"] == 1
                else "not-proven",
                "basis": (
                    "the real DBAPI commit completed, acknowledgement fault fired, and "
                    "publish_final_report returned its artifact id"
                ),
            },
            "manualReadOnlyConfirmation": {
                "performedBy": "R2 harness after production returned",
                "productionAutomaticReconcile": False,
                "finalCommitState": manual_state,
            },
            "objectStore": storage.evidence(),
            "beforePublication": before,
            "databaseFacts": facts,
            "duplicateArtifactAndTerminalFactsAbsent": duplicate_free,
        }

    def _case_absent_precommit_fault(self) -> dict[str, Any]:
        fixture, lease, before = self._prepare_publication_case(
            "r2-publication-absent-precommit"
        )
        storage = _ObjectStoreProbe(self.temp_path / "publication-absent-precommit")
        caught: BaseException | None = None
        with self.sessions() as db:
            fault = self._install_precommit_fault(db)
            try:
                self._publish(
                    db,
                    lease=lease,
                    storage=storage,
                    committed_session_factory=self.sessions,
                )
            except BaseException as error:  # noqa: BLE001 - evidence records exact outcome
                caught = error
        after = self.snapshot(fixture.run_id)
        facts = self._publication_facts(fixture.run_id, lease.attempt_id)
        object_evidence = storage.evidence()
        prepublication_preserved = (
            after == before and self._absent_terminal_facts_are_zero(facts)
        )
        absent_proven = (
            type(caught) is _PrecommitRejected
            and fault["fired"] == 1
            and object_evidence["cleanupCalls"] == [storage.publication["objectKey"]]
            and object_evidence["retainedObjectCount"] == 0
            and prepublication_preserved
        )
        passed = absent_proven
        return {
            "name": "absent-precommit-fault-cleans-once",
            "status": "pass" if passed else "fail",
            "fault": fault,
            "callerOutcome": (
                {"kind": "raised", "error": error_json(caught)}
                if caught is not None
                else {"kind": "returned"}
            ),
            "productionClassificationEvidence": {
                "state": "absent" if absent_proven else "not-proven",
                "basis": (
                    "before_commit rejected the real transaction; production verification "
                    "found no committed publication, cleaned once, and re-raised the fault"
                ),
            },
            "objectStore": object_evidence,
            "beforePublication": before,
            "afterPublication": after,
            "databaseFacts": facts,
            "databasePrepublicationStatePreserved": prepublication_preserved,
        }

    def _case_unknown_committed(self) -> dict[str, Any]:
        fixture, lease, before = self._prepare_publication_case(
            "r2-publication-unknown-committed"
        )
        storage = _ObjectStoreProbe(self.temp_path / "publication-unknown-committed")
        caught: BaseException | None = None
        with self.sessions() as db, self._commit_ack_loss(db) as fault:
            try:
                self._publish(
                    db,
                    lease=lease,
                    storage=storage,
                    committed_session_factory=self._unavailable_session_factory,
                )
            except BaseException as error:  # noqa: BLE001 - expected unknown outcome
                caught = error
        retained_before_manual = storage.evidence()
        manual_state = self._manual_final_commit_state(
            fixture=fixture,
            lease=lease,
            storage=storage,
        )
        facts = self._publication_facts(fixture.run_id, lease.attempt_id)
        duplicate_free = self._committed_terminal_facts_are_unique(facts)
        unknown_raised = (
            isinstance(caught, ResearchError)
            and caught.code == "research_commit_outcome_unknown"
        )
        passed = (
            unknown_raised
            and fault["fired"] == 1
            and retained_before_manual["cleanupCalls"] == []
            and retained_before_manual["retainedObjectCount"] == 1
            and manual_state == "committed"
            and duplicate_free
        )
        return {
            "name": "unknown-committed-retains-then-manual-classification",
            "status": "pass" if passed else "fail",
            "fault": fault,
            "callerOutcome": (
                {"kind": "raised", "error": error_json(caught)}
                if caught is not None
                else {"kind": "returned"}
            ),
            "productionUnknownOutcome": unknown_raised,
            "objectStoreBeforeManualClassification": retained_before_manual,
            "manualReadOnlyClassification": {
                "performedBy": "R2 harness after publish_final_report returned unknown",
                "productionAutomaticReconcile": False,
                "function": "citeframe_research_persistence.publication._final_commit_state",
                "finalCommitState": manual_state,
            },
            "objectStoreAfterManualClassification": storage.evidence(),
            "beforePublication": before,
            "databaseFacts": facts,
            "duplicateArtifactAndTerminalFactsAbsent": duplicate_free,
        }

    def _case_unknown_absent_manual_compensation(self) -> dict[str, Any]:
        fixture, lease, before = self._prepare_publication_case(
            "r2-publication-unknown-absent"
        )
        storage = _ObjectStoreProbe(self.temp_path / "publication-unknown-absent")
        caught: BaseException | None = None
        with self.sessions() as db:
            fault = self._install_precommit_fault(db)
            try:
                self._publish(
                    db,
                    lease=lease,
                    storage=storage,
                    committed_session_factory=self._unavailable_session_factory,
                )
            except BaseException as error:  # noqa: BLE001 - expected unknown outcome
                caught = error
        retained_before_manual = storage.evidence()
        manual_state = self._manual_final_commit_state(
            fixture=fixture,
            lease=lease,
            storage=storage,
        )
        unknown_raised = (
            isinstance(caught, ResearchError)
            and caught.code == "research_commit_outcome_unknown"
        )
        before_compensation_facts = self._publication_facts(
            fixture.run_id, lease.attempt_id
        )
        if unknown_raised and manual_state == "absent":
            storage.cleanup(storage.publication["objectKey"])
        after_compensation = storage.evidence()
        after = self.snapshot(fixture.run_id)
        after_compensation_facts = self._publication_facts(
            fixture.run_id, lease.attempt_id
        )
        prepublication_preserved = (
            after == before
            and before_compensation_facts == after_compensation_facts
            and self._absent_terminal_facts_are_zero(after_compensation_facts)
        )
        passed = (
            unknown_raised
            and fault["fired"] == 1
            and retained_before_manual["cleanupCalls"] == []
            and retained_before_manual["retainedObjectCount"] == 1
            and manual_state == "absent"
            and after_compensation["cleanupCalls"] == [storage.publication["objectKey"]]
            and after_compensation["retainedObjectCount"] == 0
            and prepublication_preserved
        )
        return {
            "name": "unknown-absent-retains-then-manual-compensation",
            "status": "pass" if passed else "fail",
            "fault": fault,
            "callerOutcome": (
                {"kind": "raised", "error": error_json(caught)}
                if caught is not None
                else {"kind": "returned"}
            ),
            "productionUnknownOutcome": unknown_raised,
            "objectStoreBeforeManualClassification": retained_before_manual,
            "manualReadOnlyClassification": {
                "performedBy": "R2 harness after publish_final_report returned unknown",
                "productionAutomaticReconcile": False,
                "function": "citeframe_research_persistence.publication._final_commit_state",
                "finalCommitState": manual_state,
            },
            "manualCompensation": {
                "performedBy": "R2 harness only after manual absent classification",
                "productionAutomaticCompensation": False,
                "cleanupCallCount": len(after_compensation["cleanupCalls"]),
            },
            "objectStoreAfterManualCompensation": after_compensation,
            "beforePublication": before,
            "afterManualCompensation": after,
            "databaseFactsBeforeCompensation": before_compensation_facts,
            "databaseFactsAfterCompensation": after_compensation_facts,
            "databasePrepublicationStatePreserved": prepublication_preserved,
        }

    def _prepare_publication_case(self, name: str) -> tuple[Any, Any, dict[str, Any]]:
        fixture = self.base.seed_run(name)
        prompt_id = self.seed_prompt(fixture, "synthesizer")
        step_key = f"artifact-publisher:{name}"
        with self.sessions() as db:
            step = db.get(ResearchStep, fixture.step_ids[0])
            if step is None:
                raise AssertionError("publication fixture Step is missing")
            step.step_kind = "artifact_publisher"
            step.step_key = step_key
            step.branch_key = None
            step.prompt_version_id = prompt_id
            db.commit()
        self.seed_queued_events(fixture)
        with self.sessions() as db:
            lease = claim_specific_research_step(
                db,
                run_id=fixture.run_id,
                step_key=step_key,
                branch_key=None,
                worker_instance_id=f"{name}-worker",
                now=utcnow(),
            )
            db.commit()
        return fixture, lease, self.snapshot(fixture.run_id)

    def _publish(
        self,
        db: Session,
        *,
        lease: Any,
        storage: _ObjectStoreProbe,
        committed_session_factory: Callable[[], Session],
    ) -> str:
        return publish_final_report(
            db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            fact_claim_ids=(),
            unresolved_claim_ids=(),
            store_bytes=storage.store,
            cleanup_bytes=storage.cleanup,
            committed_session_factory=committed_session_factory,
            prompt_loader=self._prompt_loader,
        )

    @staticmethod
    def _prompt_loader(
        db: Session,
        snapshot: ResearchExecutionSnapshot,
    ) -> list[dict[str, object]]:
        rows = list(
            db.scalars(
                select(ResearchExecutionPromptVersion).where(
                    ResearchExecutionPromptVersion.execution_snapshot_id == snapshot.id
                )
            ).all()
        )
        return [
            {"nodeKey": row.node_key, "promptVersionId": row.prompt_version_id}
            for row in rows
        ]

    @staticmethod
    def _unavailable_session_factory() -> Session:
        raise RuntimeError("R2 injected commit-classification session outage")

    @staticmethod
    def _install_precommit_fault(db: Session) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "mechanism": "SQLAlchemy Session.before_commit event",
            "timing": "before DBAPI commit",
            "fired": 0,
        }

        def reject_before_commit(_session: Session) -> None:
            evidence["fired"] += 1
            raise _PrecommitRejected("R2 injected precommit rejection")

        event.listen(db, "before_commit", reject_before_commit, once=True)
        return evidence

    @staticmethod
    @contextmanager
    def _commit_ack_loss(db: Session) -> Iterator[dict[str, Any]]:
        """Commit through the real dialect once, then hide its acknowledgement."""
        dialect = db.get_bind().dialect
        original = dialect.do_commit
        had_instance_override = "do_commit" in dialect.__dict__
        previous_instance_override = dialect.__dict__.get("do_commit")
        evidence: dict[str, Any] = {
            "mechanism": "one-shot SQLAlchemy dialect.do_commit fault wrapper",
            "timing": "after real DBAPI commit, before SQLAlchemy receives success",
            "fired": 0,
            "afterCommitEventBlocker": (
                "SQLAlchemy Session.after_commit fires after the Session transaction enters "
                "COMMITTED; raising there makes production db.rollback raise InvalidRequestError "
                "before _final_commit_state can run, so it cannot cleanly model ACK loss"
            ),
        }

        def commit_then_drop_ack(dbapi_connection: Any) -> None:
            original(dbapi_connection)
            if evidence["fired"] == 0:
                evidence["fired"] = 1
                raise _CommitAcknowledgementLost(
                    "R2 injected commit acknowledgement loss"
                )

        dialect.do_commit = commit_then_drop_ack
        try:
            yield evidence
        finally:
            if had_instance_override:
                dialect.do_commit = previous_instance_override
            else:
                del dialect.do_commit

    def _manual_final_commit_state(
        self,
        *,
        fixture: Any,
        lease: Any,
        storage: _ObjectStoreProbe,
    ) -> str:
        publication = storage.publication
        return _final_commit_state(
            self.sessions,
            artifact_id=publication["artifactId"],
            run_id=fixture.run_id,
            step_id=lease.step_id,
            attempt_id=lease.attempt_id,
            artifact_sha256=publication["contentSha256"],
            object_key=publication["objectKey"],
        )

    def _publication_facts(self, run_id: str, attempt_id: str) -> dict[str, Any]:
        with self.sessions() as db:
            artifacts = list(
                db.scalars(
                    select(ResearchArtifact)
                    .where(ResearchArtifact.run_id == run_id)
                    .order_by(ResearchArtifact.id)
                ).all()
            )
            run = db.get(ResearchRun, run_id)
            step = db.scalar(select(ResearchStep).where(ResearchStep.run_id == run_id))
            attempt = db.get(ResearchStepAttempt, attempt_id)
            terminal_events = list(
                db.scalars(
                    select(ResearchEvent)
                    .where(
                        ResearchEvent.run_id == run_id,
                        ResearchEvent.event_type.in_(_TERMINAL_EVENT_TYPES),
                    )
                    .order_by(ResearchEvent.seq)
                ).all()
            )
            event_counts = {
                event_type: sum(row.event_type == event_type for row in terminal_events)
                for event_type in _TERMINAL_EVENT_TYPES
            }
            artifact_ids = [artifact.id for artifact in artifacts]
            prompt_binding_count = (
                int(
                    db.scalar(
                        select(func.count())
                        .select_from(ResearchArtifactPromptVersion)
                        .where(
                            ResearchArtifactPromptVersion.artifact_id.in_(artifact_ids)
                        )
                    )
                    or 0
                )
                if artifact_ids
                else 0
            )
            snapshot = self.snapshot(run_id)
            return {
                "artifactCount": len(artifacts),
                "artifacts": [
                    {
                        "id": artifact.id,
                        "logicalKey": artifact.logical_key,
                        "objectKey": artifact.object_key,
                        "contentSha256": artifact.content_sha256,
                    }
                    for artifact in artifacts
                ],
                "artifactPromptBindingCount": prompt_binding_count,
                "terminalEventCounts": event_counts,
                "terminalEvents": [
                    {
                        "seq": event_row.seq,
                        "type": event_row.event_type,
                        "dedupeKey": event_row.dedupe_key,
                        "artifactIds": event_row.payload_json.get("artifactIds"),
                        "artifactId": event_row.payload_json.get("artifactId"),
                        "finalArtifactId": event_row.payload_json.get(
                            "finalArtifactId"
                        ),
                    }
                    for event_row in terminal_events
                ],
                "runStatus": None if run is None else run.status,
                "stepStatus": None if step is None else step.status,
                "attemptStatus": None if attempt is None else attempt.status,
                "attemptOutputSha256": None
                if attempt is None
                else attempt.output_sha256,
                "eventOracle": self.event_oracle(
                    snapshot,
                    require_terminal_run_last=bool(artifacts),
                ),
            }

    @staticmethod
    def _committed_terminal_facts_are_unique(facts: dict[str, Any]) -> bool:
        artifact = facts["artifacts"][0] if len(facts["artifacts"]) == 1 else None
        if artifact is None:
            return False
        artifact_id = artifact["id"]
        return (
            facts["artifactCount"] == 1
            and artifact["logicalKey"] == "final-report"
            and facts["artifactPromptBindingCount"] == 1
            and facts["terminalEventCounts"]
            == {
                "step_succeeded": 1,
                "artifact_published": 1,
                "run_completed": 1,
            }
            and facts["terminalEvents"]
            == [
                {
                    "seq": facts["terminalEvents"][0]["seq"],
                    "type": "step_succeeded",
                    "dedupeKey": facts["terminalEvents"][0]["dedupeKey"],
                    "artifactIds": [artifact_id],
                    "artifactId": None,
                    "finalArtifactId": None,
                },
                {
                    "seq": facts["terminalEvents"][1]["seq"],
                    "type": "artifact_published",
                    "dedupeKey": f"artifact-published:{artifact_id}",
                    "artifactIds": None,
                    "artifactId": artifact_id,
                    "finalArtifactId": None,
                },
                {
                    "seq": facts["terminalEvents"][2]["seq"],
                    "type": "run_completed",
                    "dedupeKey": f"run-completed:{artifact_id}",
                    "artifactIds": None,
                    "artifactId": None,
                    "finalArtifactId": artifact_id,
                },
            ]
            and facts["runStatus"] == "completed"
            and facts["stepStatus"] == "succeeded"
            and facts["attemptStatus"] == "succeeded"
            and facts["attemptOutputSha256"] == artifact["contentSha256"]
            and all(facts["eventOracle"].values())
        )

    @staticmethod
    def _absent_terminal_facts_are_zero(facts: dict[str, Any]) -> bool:
        return (
            facts["artifactCount"] == 0
            and facts["artifactPromptBindingCount"] == 0
            and facts["terminalEventCounts"]
            == {
                "step_succeeded": 0,
                "artifact_published": 0,
                "run_completed": 0,
            }
            and facts["terminalEvents"] == []
            and facts["runStatus"] == "running"
            and facts["stepStatus"] == "running"
            and facts["attemptStatus"] == "running"
            and facts["attemptOutputSha256"] is None
            and all(facts["eventOracle"].values())
        )

    def _publication_evidence_binding(self) -> dict[str, Any]:
        self.verify_source_snapshot()
        scenario_path = self.repo_root / _SCENARIO_SOURCE
        publication_proof = self.source_snapshot["productionFiles"].get(
            _PUBLICATION_SOURCE
        )
        if publication_proof is None:
            raise AssertionError(
                "publication.py is absent from the production source manifest"
            )
        return {
            "baseHead": self.source_snapshot["baseHead"],
            "candidateSourceManifestSha256": self.source_snapshot[
                "candidateSourceManifestSha256"
            ],
            "publicationProductionSource": {
                "path": _PUBLICATION_SOURCE,
                **publication_proof,
            },
            "controllerHarnessSourceSha256": dict(self.harness_source_hashes),
            "publicationScenarioSource": {
                "path": _SCENARIO_SOURCE,
                "sha256": hashlib.sha256(scenario_path.read_bytes()).hexdigest(),
            },
        }


__all__ = ("PublicationOutcomeScenarios",)
