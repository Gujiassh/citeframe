"""Durable call admission and metadata-only settlement using native arithmetic callbacks."""
from dataclasses import asdict, dataclass
from uuid import uuid4

from sqlalchemy import event, func, select, update
from citeframe_contracts.compaction import AccountingReceipt, UsageSettlement
from citeframe_persistence.models import (ChatMemoryExecution, MemoryCall, MemoryUse, ResearchBudgetLedger, ResearchProviderCall,
                                         ResearchRun, ResearchStep, ResearchStepAttempt)
from .guards import canonical, digest, lock_one
from .policy import CompactionError


@dataclass(frozen=True)
class NativeAccounting:
    """Composition supplies unmodified native reserve/send/reconcile functions, never content authority."""
    reserve: object
    mark_sent: object
    reconcile: object


def invoke(db, callback, *args, **kwargs):
    def forbid(session):
        raise CompactionError("callback_transaction_forbidden")
    event.listen(db, "before_commit", forbid)
    try:
        return callback(db, *args, **kwargs)
    finally:
        event.remove(db, "before_commit", forbid)


class CallJournal:
    def __init__(self, repository, *, native_accounting=None, object_store=None, max_request_bytes=1048576):
        self.repo, self.accounting = repository, native_accounting
        if type(max_request_bytes) is not int or max_request_bytes<=0:raise CompactionError("invalid_request_archive_limit")
        self.object_store,self.max_request_bytes=object_store,max_request_bytes

    def archive_request(self,captured,policy,receipt,request,*,dispatch_profile=None,compaction_plan=None,summary_input=None):
        from .requests import archive_request
        return archive_request(self,captured,policy,receipt,request,dispatch_profile=dispatch_profile,compaction_plan=compaction_plan,summary_input=summary_input)

    def reserve(self, captured, policy, *, logical_key, purpose, request_sha256, input_tokens,
                output_tokens, provider, model, profile_fingerprint, next_main_input=0,
                next_main_output=0, parent_call_id=None, dispatch_profile=None,compaction_plan=None,summary_input=None):
        if (purpose not in ("main", "compact_chunk", "compact_merge") or not logical_key
                or len(logical_key) > 160 or any(type(n) is not int or n < 0 for n in
                (input_tokens,output_tokens,next_main_input,next_main_output))):
            raise CompactionError("invalid_call_reservation")
        from .rendering import input_manifest
        manifest=input_manifest(captured,policy,dispatch_profile,compaction_plan,summary_input)
        if dispatch_profile is not None and (dispatch_profile["provider"]!=provider or dispatch_profile["model"]!=model or dispatch_profile["configFingerprint"]!=profile_fingerprint):
            raise CompactionError("dispatch_binding_changed")
        def reserve(db):
            guard = self.repo.guard(db, captured.owner)
            if self.repo._capture(guard, captured.units, policy) != captured:
                raise CompactionError("context_changed")
            owner_column = MemoryCall.chat_execution_id if captured.owner.kind == "chat" else MemoryCall.research_attempt_id
            if captured.owner.kind == "chat":
                owners = guard.retry_owner_ids()
                scope = owner_column.in_(owners)
            else:
                scope = MemoryCall.research_budget_ledger_id == guard.ledger.id
            rows = list(db.scalars(select(MemoryCall).where(scope).order_by(MemoryCall.id).with_for_update(nowait=True)))
            if any(r.purpose=="tool_group" and r.state in ("reserved","sent","outcome_unknown") for r in rows):
                raise CompactionError("incomplete_tool_batch")
            for row in rows:
                if row.policy_fingerprint != captured.policy_fingerprint:
                    raise CompactionError("context_policy_changed")
                if (row.chat_execution_id or row.research_attempt_id) == captured.owner.owner_id and row.logical_key == logical_key:
                    if row.request_sha256 != request_sha256 or row.purpose != purpose or canonical(row.input_manifest)!=canonical(manifest):
                        raise CompactionError("call_idempotency_conflict")
                    if row.state in ("sent", "outcome_unknown"):
                        raise CompactionError("call_outcome_unknown")
                    return self._receipt(row)
            billed = [r for r in rows if not (r.result_manifest or {}).get("no_dispatch")]
            inputs = sum(r.actual_input if r.reservation_state == "settled" and r.actual_input is not None
                         else r.reserved_input for r in billed)
            outputs = sum(r.actual_output if r.reservation_state == "settled" and r.actual_output is not None
                          else r.reserved_output for r in billed)
            summaries = sum(r.purpose in ("compact_chunk", "compact_merge") for r in billed)
            if (len(billed) + 1 + (purpose != "main") > policy["maxCalls"]
                    or inputs + input_tokens + next_main_input > policy["maxInputTokens"]
                    or outputs + output_tokens + next_main_output > policy["maxOutputTokens"]
                    or (purpose != "main" and summaries >= policy["maxSummaryCalls"])):
                raise CompactionError("context_budget_exhausted")
            native_id = ledger_id = None
            if captured.owner.kind == "research":
                if self.accounting is None: raise CompactionError("native_accounting_required")
                reservation = invoke(db, self.accounting.reserve, attempt_id=captured.owner.owner_id,
                    logical_call_key=logical_key, request_sha256=request_sha256, provider=provider, model=model,
                    provider_config_fingerprint=profile_fingerprint, reserved_input_tokens=input_tokens,
                    reserved_output_tokens=output_tokens, now=self.repo.clock())
                native_id, ledger_id = reservation.provider_call_id, reservation.budget_ledger_id
                if ledger_id != guard.ledger.id: raise CompactionError("native_ledger_changed")
            if parent_call_id:
                parent = lock_one(db, MemoryCall, parent_call_id)
                if parent is None or (parent.chat_execution_id or parent.research_attempt_id) != captured.owner.owner_id:
                    raise CompactionError("call_parent_invalid")
            row = MemoryCall(id=str(uuid4()), workspace_id=captured.owner.workspace_id,
                actor_user_id=captured.owner.actor_user_id,
                chat_execution_id=captured.owner.owner_id if captured.owner.kind == "chat" else None,
                research_attempt_id=captured.owner.owner_id if captured.owner.kind == "research" else None,
                purpose=purpose, logical_key=logical_key, ordinal=len(rows), parent_call_id=parent_call_id,
                native_provider_call_id=native_id, native_tool_call_id=None, research_budget_ledger_id=ledger_id,
                provider_tool_call_id=None, state="reserved", context_version=captured.context_version,
                checkpoint_id=captured.checkpoint_id, input_manifest=manifest, request_object_key=None, request_sha256=request_sha256,
                result_object_key=None, result_sha256=None, result_state="absent", result_manifest=None,
                result_tokens=None, policy_fingerprint=captured.policy_fingerprint, reserved_input=input_tokens,
                reserved_output=output_tokens, actual_input=None, actual_output=None, usage_source="unknown",
                cost_microunits=None, reservation_state="reserved", no_progress_boundary_sha256=None,
                created_at=self.repo.clock(), sent_at=None, settled_at=None)
            if len(canonical(row.input_manifest).encode()) > 131072:
                raise CompactionError("context_too_large")
            db.add(row); db.flush()
            dependencies=[(u.source.source_id if u.source else None,None,u.tool_group_id) for u in captured.units]
            if captured.checkpoint_id: dependencies.append((None,captured.checkpoint_id,None))
            for unit in captured.units:
                if unit.tool_group_id:
                    group=db.get(MemoryCall,unit.tool_group_id)
                    for ref in group.result_manifest.get("sources",[]):
                        leaf=(ref["source_id"],None,None)
                        if leaf not in dependencies: dependencies.append(leaf)
            for source_id,snapshot_id,tool_id in dependencies:
                db.add(MemoryUse(id=str(uuid4()),workspace_id=captured.owner.workspace_id,
                    consumer_revision_id=None,consumer_snapshot_id=None,consumer_call_id=row.id,consumer_call_part="input",
                    source_id=source_id,used_snapshot_id=snapshot_id,used_tool_call_id=tool_id,
                    use_mode="context",atom_key="input",support_group="original",relation="context"))
            db.flush(); self.repo.fault("reservation")
            return self._receipt(row)
        return self.repo.transact(reserve)

    @staticmethod
    def _receipt(row):
        return AccountingReceipt(row.id, row.workspace_id, row.chat_execution_id or row.research_attempt_id,
                                 row.request_sha256,row.native_provider_call_id,row.research_budget_ledger_id)

    def mark_sent(self, captured, policy, receipt, *, require_archive=False,dispatch_profile=None,compaction_plan=None,summary_input=None):
        def send(db):
            guard = self.repo.guard(db, captured.owner,receipt.native_provider_call_id)
            if self.repo._capture(guard,captured.units,policy) != captured: raise CompactionError("context_changed")
            row = lock_one(db, MemoryCall, receipt.call_id)
            if (row is None or self._receipt(row) != receipt or row.state != "reserved"
                    or receipt.workspace_id != captured.owner.workspace_id or receipt.owner_id != captured.owner.owner_id
                    or row.context_version != captured.context_version
                    or canonical(row.input_manifest.get("capture")) != canonical(asdict(captured))):
                raise CompactionError("call_not_sendable")
            from .rendering import match_input
            match_input(row,captured,policy,dispatch_profile,compaction_plan,summary_input)
            if require_archive and not row.request_object_key:raise CompactionError("request_archive_required")
            if row.native_provider_call_id:
                if self.accounting is None: raise CompactionError("native_accounting_required")
                invoke(db,self.accounting.mark_sent,row.native_provider_call_id,now=self.repo.clock())
            row.state, row.sent_at = "sent", self.repo.clock()
            db.flush()
        return self.repo.transact(send)

    def settle(self, receipt: AccountingReceipt, usage: UsageSettlement):
        """No membership/source/object authority. No ORM object escapes this fresh transaction."""
        def settle(db):
            native = None
            if receipt.native_provider_call_id:
                located = db.execute(select(ResearchProviderCall.run_id,ResearchProviderCall.step_id,
                    ResearchProviderCall.attempt_id,ResearchProviderCall.budget_ledger_id).where(
                    ResearchProviderCall.id == receipt.native_provider_call_id)).first()
                if located is None: raise CompactionError("accounting_receipt_invalid")
                run = lock_one(db,ResearchRun,located.run_id)
                step = lock_one(db,ResearchStep,located.step_id)
                attempt = lock_one(db,ResearchStepAttempt,located.attempt_id)
                native = lock_one(db,ResearchProviderCall,receipt.native_provider_call_id)
                ledger = lock_one(db,ResearchBudgetLedger,located.budget_ledger_id)
                if (any(row is None or row.workspace_id != receipt.workspace_id for row in (run,step,attempt,native,ledger))
                        or native.attempt_id != receipt.owner_id or native.budget_ledger_id != receipt.native_ledger_id
                        or native.request_sha256 != receipt.request_sha256 or attempt.step_id != step.id
                        or step.run_id != run.id or native.step_id != step.id or native.run_id != run.id):
                    raise CompactionError("accounting_receipt_invalid")
            fields = (MemoryCall.id, MemoryCall.workspace_id, MemoryCall.chat_execution_id,
                      MemoryCall.research_attempt_id, MemoryCall.request_sha256, MemoryCall.native_provider_call_id,
                      MemoryCall.research_budget_ledger_id, MemoryCall.state, MemoryCall.reservation_state,
                      MemoryCall.reserved_input, MemoryCall.reserved_output, MemoryCall.actual_input,
                      MemoryCall.actual_output, MemoryCall.usage_source)
            row = db.execute(select(*fields).where(MemoryCall.id == receipt.call_id).with_for_update(nowait=True)).first()
            if row is None or self._receipt(row) != receipt: raise CompactionError("accounting_receipt_invalid")
            if row.reservation_state == "settled":
                if (row.state,row.actual_input,row.actual_output,row.usage_source) != (
                        usage.state,usage.input_tokens,usage.output_tokens,
                        "estimated" if native is not None and usage.source != "reported" else usage.source) and row.state not in ("outcome_unknown","cancelled"):
                    raise CompactionError("accounting_receipt_conflict")
                return dict(state=row.state,input_tokens=row.actual_input,output_tokens=row.actual_output)
            cancelled_unsent = native is not None and native.status == "cancelled" and row.state == "reserved"
            if row.state not in ("sent", "outcome_unknown") and not cancelled_unsent:
                raise CompactionError("call_not_settleable")
            state, input_tokens, output_tokens, source = usage.state,usage.input_tokens,usage.output_tokens,usage.source
            if native:
                if native.status == "sent":
                    if self.accounting is None: raise CompactionError("native_accounting_required")
                    invoke(db,self.accounting.reconcile,provider_call_id=native.id,status=usage.state,
                        actual_input_tokens=usage.input_tokens,actual_output_tokens=usage.output_tokens,
                        usage_source="actual" if usage.source == "reported" else "estimated",
                        usage_final=usage.source == "reported" and usage.state != "outcome_unknown",now=self.repo.clock())
                    db.flush(); self.repo.fault("native_settlement")
                elif native.status not in ("succeeded","failed","outcome_unknown","cancelled"):
                    raise CompactionError("native_call_not_settleable")
                state=native.status
                input_tokens=native.actual_input_tokens if native.actual_input_tokens is not None else native.reserved_input_tokens
                output_tokens=native.actual_output_tokens if native.actual_output_tokens is not None else native.reserved_output_tokens
                source="reported" if native.usage_source == "actual" else "estimated"
                if native.status == "cancelled":
                    input_tokens=output_tokens=0
            elif state == "outcome_unknown":
                input_tokens=max(input_tokens,row.reserved_input); output_tokens=max(output_tokens,row.reserved_output)
            changed=db.execute(update(MemoryCall).where(MemoryCall.id==receipt.call_id,
                MemoryCall.reservation_state=="reserved").values(state=state,actual_input=input_tokens,
                actual_output=output_tokens,usage_source=source,reservation_state="settled",settled_at=self.repo.clock()))
            if changed.rowcount != 1: raise CompactionError("accounting_receipt_conflict")
            self.repo.fault("sidecar_settlement")
            return dict(state=state,input_tokens=input_tokens,output_tokens=output_tokens)
        return self.repo.transact(settle)

    def save_summary(self,captured,policy,receipt,summary):
        from .summary import validate_summary
        def save(db):
            guard=self.repo.guard(db,captured.owner)
            if self.repo._capture(guard,captured.units,policy)!=captured: raise CompactionError("context_changed")
            row=lock_one(db,MemoryCall,receipt.call_id)
            if (row is None or self._receipt(row)!=receipt or row.state!="succeeded" or row.result_state not in ("absent","valid")
                    or receipt.workspace_id!=captured.owner.workspace_id or receipt.owner_id!=captured.owner.owner_id
                    or row.context_version!=captured.context_version or canonical(row.input_manifest.get("capture"))!=canonical(asdict(captured))
                    or row.purpose not in ("compact_chunk","compact_merge")):
                raise CompactionError("summary_call_unavailable")
            from .rendering import validate_result
            if row.result_state=="valid" and row.result_sha256!=digest(summary):raise CompactionError("summary_result_conflict")
            result=validate_result(db,row,summary,saved=row.result_state=="valid")
            if row.result_state=="valid":return
            row.result_manifest=result
            row.result_sha256=digest(summary); row.result_state="valid"
            db.flush()
        return self.repo.transact(save)

    def no_progress(self,captured,policy,boundary,reason=None):
        def operate(db):
            guard=self.repo.guard(db,captured.owner)
            if self.repo._capture(guard,captured.units,policy)!=captured: raise CompactionError("context_changed")
            owner_column=MemoryCall.chat_execution_id if captured.owner.kind=="chat" else MemoryCall.research_attempt_id
            row=db.scalar(select(MemoryCall).where(owner_column==captured.owner.owner_id,
                MemoryCall.logical_key=="no-progress:"+boundary).with_for_update(nowait=True))
            if row: return True
            if reason is None: return False
            row=MemoryCall(id=str(uuid4()),workspace_id=captured.owner.workspace_id,
                actor_user_id=captured.owner.actor_user_id,
                chat_execution_id=captured.owner.owner_id if captured.owner.kind=="chat" else None,
                research_attempt_id=captured.owner.owner_id if captured.owner.kind=="research" else None,
                purpose="compact_chunk",logical_key="no-progress:"+boundary,ordinal=0,parent_call_id=None,
                native_provider_call_id=None,native_tool_call_id=None,
                research_budget_ledger_id=guard.ledger.id if guard.ledger else None,provider_tool_call_id=None,
                state="succeeded",context_version=captured.context_version,checkpoint_id=captured.checkpoint_id,
                input_manifest={"schemaVersion":"compaction-input-v1","capture":asdict(captured),"policy":policy},
                request_object_key=None,request_sha256=boundary,result_object_key=None,result_sha256=None,
                result_state="absent",result_manifest={"no_dispatch":True,"reason":reason},result_tokens=0,
                policy_fingerprint=captured.policy_fingerprint,reserved_input=0,reserved_output=0,
                actual_input=0,actual_output=0,usage_source="estimated",cost_microunits=None,
                reservation_state="settled",no_progress_boundary_sha256=boundary,created_at=self.repo.clock(),
                sent_at=None,settled_at=self.repo.clock())
            db.add(row);db.flush()
            return True
        return self.repo.transact(operate)

    def recovered_summary(self,captured,policy,logical_key,request_sha256,*,dispatch_profile=None,compaction_plan=None,summary_input=None):
        def read(db):
            guard=self.repo.guard(db,captured.owner)
            if self.repo._capture(guard,captured.units,policy)!=captured: raise CompactionError("context_changed")
            owner_column=MemoryCall.chat_execution_id if captured.owner.kind=="chat" else MemoryCall.research_attempt_id
            row=db.scalar(select(MemoryCall).where(owner_column==captured.owner.owner_id,
                MemoryCall.logical_key==logical_key).with_for_update(nowait=True))
            if row is None: return None
            from .rendering import match_input,validate_result
            match_input(row,captured,policy,dispatch_profile,compaction_plan,summary_input)
            if row.request_sha256!=request_sha256: raise CompactionError("call_idempotency_conflict")
            if row.state in ("sent","outcome_unknown"): raise CompactionError("call_outcome_unknown")
            if row.state=="succeeded" and row.result_state=="valid":
                validate_result(db,row,row.result_manifest["summary"],saved=True)
                return row.id,row.result_manifest["summary"]
            if row.state in ("failed","cancelled"): raise CompactionError("summary_attempt_failed")
            return None
        return self.repo.transact(read)
