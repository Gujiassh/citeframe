"""Exact request objects and crash/revoke boundaries, using real migrated persistence."""
from dataclasses import asdict
import pytest
from sqlalchemy import text
from citeframe_contracts.memory import GenerationMessage,GenerationRequest
from test_compaction_call_fixture import FixtureJournal as CallJournal
from citeframe_memory.compaction.guards import digest,canonical
from citeframe_memory.compaction.policy import CompactionError
from test_compaction_fixture import pg43
from test_compaction_repository import prepared
from test_compaction_gate import Files


def setup(pg43,tmp_path):
    scope,repo,owner,policy,units=prepared(pg43)
    captured=repo.capture(owner,units,policy)
    request=GenerationRequest((GenerationMessage("system","trusted"),GenerationMessage("user",repo.read_source(owner,units[0].source))),100)
    journal=CallJournal(repo,object_store=Files(tmp_path))
    receipt=journal.reserve(captured,policy,logical_key="exact-request",purpose="main",request_sha256=digest(asdict(request)),
        input_tokens=100,output_tokens=100,provider="fixture",model="fixture",profile_fingerprint="f"*64)
    return scope,repo,owner,policy,captured,request,journal,receipt


@pytest.mark.parametrize("stage",["request_object_written","request_readback","request_adoption","after_commit"])
def test_archive_crash_recovery_keeps_unsent_exact_payload(pg43,tmp_path,stage):
    scope,repo,owner,policy,captured,request,journal,receipt=setup(pg43,tmp_path)
    calls=0
    def fault(at):
        nonlocal calls
        # after_commit of initial authorization precedes object IO; target adoption acknowledgement.
        if at=="after_commit":calls+=1
        if at==stage and (stage!="after_commit" or calls==2):raise RuntimeError("lost_ack")
    repo.fault=fault
    with pytest.raises(RuntimeError,match="lost_ack"):journal.archive_request(captured,policy,receipt,request)
    repo.fault=lambda stage:None
    with pg43.connect() as db:assert db.scalar(text("SELECT state FROM memory_calls WHERE id=:id"),{"id":receipt.call_id})=="reserved"
    key=journal.archive_request(captured,policy,receipt,request)
    assert journal.object_store.get(key)==canonical(asdict(request)).encode()
    journal.mark_sent(captured,policy,receipt,require_archive=True)
    with pytest.raises(CompactionError,match="call_not_sendable"):journal.archive_request(captured,policy,receipt,request)


@pytest.mark.parametrize("mode",["corrupt","revoked","budget"])
def test_no_send_on_corruption_revoke_or_budget_denial(pg43,tmp_path,mode):
    scope,repo,owner,policy,captured,request,journal,receipt=setup(pg43,tmp_path)
    class Store(Files):
        writes=0
        def put(self,key,raw):
            self.writes+=1
            super().put(key,raw)
            if mode=="revoked":
                with pg43.begin() as db:db.execute(text("DELETE FROM workspace_memberships WHERE id=:id"),{"id":scope.membership_id})
        def get(self,key):return b"wrong" if mode=="corrupt" else super().get(key)
    journal.object_store=Store(tmp_path)
    if mode=="budget":
        with pytest.raises(CompactionError,match="context_budget_exhausted"):
            journal.reserve(captured,policy,logical_key="over-budget",purpose="main",request_sha256="e"*64,input_tokens=100001,
                output_tokens=100,provider="fixture",model="fixture",profile_fingerprint="f"*64)
        assert journal.object_store.writes==0
    else:
        with pytest.raises(CompactionError):journal.archive_request(captured,policy,receipt,request)
        with pytest.raises(CompactionError):journal.mark_sent(captured,policy,receipt,require_archive=True)
    with pg43.connect() as db:
        assert db.execute(text("SELECT state,request_object_key FROM memory_calls WHERE id=:id"),{"id":receipt.call_id}).one()==("reserved",None)


def test_missing_archive_and_oversized_request_have_no_object_effect(pg43,tmp_path):
    scope,repo,owner,policy,captured,request,journal,receipt=setup(pg43,tmp_path)
    with pytest.raises(CompactionError,match="request_archive_required"):journal.mark_sent(captured,policy,receipt,require_archive=True)
    journal.max_request_bytes=10
    with pytest.raises(CompactionError,match="request_archive_limit"):journal.archive_request(captured,policy,receipt,request)
    assert not list(tmp_path.rglob("*"))
