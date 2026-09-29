"""Complete tool-result originals, hash-verified before a group becomes consumable."""
from dataclasses import asdict
import json
from uuid import uuid4
from sqlalchemy import select
from citeframe_contracts.compaction import SourceReference
from citeframe_contracts.memory import GenerationMessage, ToolCall
from citeframe_persistence.models import MemoryCall, MemoryUse
from .guards import body_hash, canonical, digest, lock_one
from .policy import CompactionError
from .sources import read_registered
from .units import ContextUnit


class ToolArchive:
    def __init__(self, repository, object_store, *, max_result_bytes=16*1024*1024, max_task_bytes=64*1024*1024):
        if object_store is None or min(max_result_bytes,max_task_bytes)<=0:
            raise CompactionError("tool_archive_required")
        self.repo,self.store=repository,object_store
        self.max_result,self.max_task=max_result_bytes,max_task_bytes

    def persist(self,captured,policy,unit:ContextUnit,sources:tuple[SourceReference,...]):
        if unit.kind!="tool_group" or not sources: raise CompactionError("invalid_archived_tool_group")
        original=canonical({"messages":[asdict(m) for m in unit.messages],"states":unit.result_states}).encode()
        if len(original)>self.max_result: raise CompactionError("tool_archive_limit")
        fingerprint=body_hash(original.decode())
        def admit(db):
            guard=self.repo.guard(db,captured.owner)
            if self.repo._capture(guard,captured.units,policy)!=captured: raise CompactionError("context_changed")
            for source in sources: read_registered(guard,source)
            column=MemoryCall.chat_execution_id if captured.owner.kind=="chat" else MemoryCall.research_attempt_id
            rows=list(db.scalars(select(MemoryCall).where(column.in_(guard.retry_owner_ids()),
                MemoryCall.purpose=="tool_group").order_by(MemoryCall.id).with_for_update(nowait=True)))
            for row in rows:
                if (row.chat_execution_id or row.research_attempt_id)==captured.owner.owner_id and row.logical_key==unit.key:
                    if row.request_sha256!=fingerprint: raise CompactionError("tool_group_conflict")
                    if row.state!="succeeded": raise CompactionError("tool_archive_incomplete")
                    return row.id,row.result_object_key,True
            if sum((r.result_manifest or {}).get("archiveBytes",0) for r in rows)+len(original)>self.max_task:
                raise CompactionError("tool_archive_limit")
            id_=str(uuid4());key="compaction/"+captured.owner.workspace_id+"/"+captured.owner.owner_id+"/"+id_
            db.add(MemoryCall(id=id_,workspace_id=captured.owner.workspace_id,actor_user_id=captured.owner.actor_user_id,
                chat_execution_id=captured.owner.owner_id if captured.owner.kind=="chat" else None,
                research_attempt_id=captured.owner.owner_id if captured.owner.kind=="research" else None,
                purpose="tool_group",logical_key=unit.key,ordinal=len(rows),parent_call_id=None,native_provider_call_id=None,
                native_tool_call_id=None,research_budget_ledger_id=guard.ledger.id if guard.ledger else None,
                provider_tool_call_id=None,state="reserved",context_version=captured.context_version,
                checkpoint_id=captured.checkpoint_id,input_manifest={"schemaVersion":"compaction-input-v1","capture":asdict(captured)},
                request_object_key=None,request_sha256=fingerprint,result_object_key=key,result_sha256=None,result_state="absent",
                result_manifest={"complete":False,"archiveBytes":len(original),"sources":[asdict(r) for r in sources]},
                result_tokens=None,policy_fingerprint=captured.policy_fingerprint,reserved_input=0,reserved_output=0,
                actual_input=None,actual_output=None,usage_source="unknown",cost_microunits=None,reservation_state="reserved",
                no_progress_boundary_sha256=None,created_at=self.repo.clock(),sent_at=None,settled_at=None))
            db.flush();return id_,key,False
        id_,key,replayed=self.repo.transact(admit)
        if replayed:return id_
        try:
            self.store.put(key,original)
            stored=self.store.get(key)
            if stored!=original: raise CompactionError("tool_archive_readback_mismatch")
        except Exception:
            def fail(db):
                row=lock_one(db,MemoryCall,id_)
                if row and row.state=="reserved":
                    row.state="failed";row.reservation_state="settled";row.settled_at=self.repo.clock()
            self.repo.transact(fail)
            raise CompactionError("tool_archive_failed") from None
        def finish(db):
            guard=self.repo.guard(db,captured.owner)
            if self.repo._capture(guard,captured.units,policy)!=captured:raise CompactionError("context_changed")
            for source in sources:read_registered(guard,source)
            row=lock_one(db,MemoryCall,id_)
            if row is None or row.state!="reserved":raise CompactionError("tool_archive_changed")
            row.state="succeeded";row.reservation_state="settled";row.settled_at=self.repo.clock()
            row.result_state="valid";row.result_sha256=fingerprint
            row.result_manifest={**row.result_manifest,"complete":True,"callIds":[c.call_id for c in unit.messages[0].tool_calls]}
            row.actual_input=row.actual_output=0
            for source in sources:
                db.add(MemoryUse(id=str(uuid4()),workspace_id=captured.owner.workspace_id,consumer_revision_id=None,
                    consumer_snapshot_id=None,consumer_call_id=id_,consumer_call_part="result",source_id=source.source_id,
                    used_snapshot_id=None,used_tool_call_id=None,use_mode="context",atom_key="original",support_group="tool",relation="context"))
            db.flush()
        self.repo.transact(finish)
        return id_

    def read(self,owner,group_id):
        def metadata(db):
            guard=self.repo.guard(db,owner);row=lock_one(db,MemoryCall,group_id)
            if (row is None or row.workspace_id!=owner.workspace_id or (row.chat_execution_id or row.research_attempt_id)!=owner.owner_id
                    or row.purpose!="tool_group" or row.state!="succeeded" or row.result_state!="valid"
                    or not row.result_manifest.get("complete")):
                raise CompactionError("tool_group_unavailable")
            for ref in row.result_manifest["sources"]:read_registered(guard,SourceReference(**ref))
            return row.result_object_key,row.result_sha256,row.result_manifest["archiveBytes"],row.logical_key
        before=self.repo.transact(metadata)
        body=self.store.get(before[0])
        if len(body)!=before[2] or body_hash(body.decode())!=before[1]:raise CompactionError("tool_archive_readback_mismatch")
        if self.repo.transact(metadata)!=before:raise CompactionError("tool_archive_changed")
        raw=json.loads(body)
        messages=tuple(GenerationMessage(m["role"],m["content"],tuple(ToolCall(**c) for c in m["tool_calls"]),m["tool_call_id"]) for m in raw["messages"])
        return ContextUnit(before[3],"tool_group",messages,tuple(raw["states"]))

    def read_range(self,owner,group_id,call_id,*,start,end):
        unit=self.read(owner,group_id)
        for message in unit.messages[1:]:
            if message.tool_call_id==call_id:
                if type(start) is not int or type(end) is not int or not 0<=start<=end<=len(message.content):
                    raise CompactionError("invalid_source_range")
                return message.content[start:end]
        raise CompactionError("tool_call_unavailable")
