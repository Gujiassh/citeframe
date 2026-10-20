"""Bounded exact provider request durability before any provider send admission."""
from dataclasses import asdict
from citeframe_persistence.models import MemoryCall
from .guards import canonical, digest, lock_one
from .policy import CompactionError


def archive_request(journal,captured,policy,receipt,request,*,dispatch_profile=None,compaction_plan=None,summary_input=None):
    if journal.object_store is None:raise CompactionError("request_archive_required")
    raw=canonical(asdict(request)).encode()
    if len(raw)>journal.max_request_bytes:raise CompactionError("request_archive_limit")
    if digest(asdict(request))!=receipt.request_sha256:raise CompactionError("dispatch_payload_changed")
    key="compaction/"+receipt.workspace_id+"/"+receipt.owner_id+"/requests/"+receipt.call_id
    def guarded(db,adopt=False):
        guard=journal.repo.guard(db,captured.owner)
        if journal.repo._capture(guard,captured.units,policy)!=captured:raise CompactionError("context_changed")
        row=lock_one(db,MemoryCall,receipt.call_id)
        if (row is None or journal._receipt(row)!=receipt or row.state!="reserved"
                or receipt.owner_id!=captured.owner.owner_id or receipt.workspace_id!=captured.owner.workspace_id
                or canonical(row.input_manifest.get("capture"))!=canonical(asdict(captured))
                or row.request_object_key not in (None,key)):
            raise CompactionError("call_not_sendable")
        from .rendering import match_input,validate_physical_summary
        match_input(row,captured,policy,dispatch_profile,compaction_plan,summary_input)
        validate_physical_summary(db,row,request)
        if adopt:row.request_object_key=key;db.flush();journal.repo.fault("request_adoption")
        return row.request_object_key
    existing=journal.repo.transact(guarded)
    if existing is None:
        journal.object_store.put(key,raw)
        journal.repo.fault("request_object_written")
    if journal.object_store.get(key)!=raw:raise CompactionError("request_archive_corrupt")
    journal.repo.fault("request_readback")
    journal.repo.transact(lambda db:guarded(db,True))
    return key
