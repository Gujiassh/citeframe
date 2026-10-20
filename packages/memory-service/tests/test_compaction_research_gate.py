"""Neutral gate and actual native accounting; deterministic provider, unchanged frozen inputs."""
from dataclasses import replace
import json
import pytest
from sqlalchemy import text
from citeframe_contracts.compaction import UsageSettlement
from citeframe_contracts.memory import GenerationRequest, GenerationMessage, ModelConnectionSnapshot, TokenCount
from citeframe_memory.compaction.gate import DispatchGate
from citeframe_memory.compaction.policy import CompactionPolicy, CounterIdentity, CompactionError
from test_compaction_fixture import pg43
from test_compaction_gate import Provider, Files
from test_compaction_intervals import ScopedProvider
from test_compaction_research import make_research, services, capture_fixture, summary, projection, PROFILE


class Counter:
    def count(self, request, connection):
        return TokenCount(sum(len(m.content)+10 for m in request.messages)//8+20,
            "estimated", "fixture", "v1", connection.config_fingerprint)


def make_gate(repository, journal, provider, *, identity="openai"):
    connection=ModelConnectionSnapshot("openai_responses", "https://fixture.invalid", "gpt-5.5", "unused", 10, PROFILE, 2500, 200)
    return DispatchGate(repository,journal,provider,Counter(),connection,
        CounterIdentity("fixture","v1","estimated",PROFILE),input_ceiling=2200,
        provider_identity=identity,policy=CompactionPolicy(soft_ratio=.5,target_ratio=.4,min_new_tokens=1,min_gain_tokens=1))


def test_research_gate_two_episodes_same_attempt_native_budget_and_exact_sources(pg43,tmp_path):
    fixture=make_research(pg43,excerpt_padding=6000)
    repository,journal=services(pg43,fixture)
    journal.object_store=Files(tmp_path)
    full=capture_fixture(repository,fixture)
    frozen=projection(pg43,["research_execution_snapshots","research_evidence_snapshots","research_evidence_handles","research_artifacts"])
    value=summary(fixture,full.units[:1])
    value["facts"][0]["text"]=value["facts"][0]["text"].split(" x")[0]
    provider=ScopedProvider()
    gate=make_gate(repository,journal,provider)
    template=GenerationRequest((GenerationMessage("system","trusted"),),200)
    first=gate.prepare_main_dispatch(fixture.owner,template,full.units[:1],fixture.policy,
        expected_context_version=0,logical_key="main-1",recent_units=0)
    assert first.disposition=="compacted"
    gate.authorize_send(first,fixture.policy)
    journal.settle(first.receipt,UsageSettlement("succeeded",50,20,"reported"))
    second=gate.prepare_main_dispatch(fixture.owner,template,full.units,fixture.policy,
        expected_context_version=1,logical_key="main-2",recent_units=0,mode="continuation")
    assert second.disposition=="compacted"
    assert second.captured.owner==first.captured.owner==fixture.owner
    assert second.captured.context_version==2 and second.checkpoint_id!=first.checkpoint_id
    gate.authorize_send(second,fixture.policy)
    journal.settle(second.receipt,UsageSettlement("succeeded",50,20,"reported"))
    assert frozen==projection(pg43,list(frozen))
    assert tuple(repository.read_source(fixture.owner,u.source) for u in full.units)==fixture.excerpts
    for mode in ("role","resume"):
        permit=gate.prepare_main_dispatch(fixture.owner,template,full.units,fixture.policy,
            expected_context_version=2,logical_key=mode,mode=mode)
        gate.authorize_send(permit,fixture.policy)
        journal.settle(permit.receipt,UsageSettlement("succeeded",50,20,"reported"))
        assert permit.checkpoint_id==second.checkpoint_id
    with pg43.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM task_memory_snapshots"))==2
        assert db.scalar(text("SELECT count(*) FROM research_provider_calls"))==len(provider.calls)+4
        assert db.execute(text("SELECT DISTINCT provider,model FROM research_provider_calls")).one()==("openai","gpt-5.5")
        ledger=db.execute(text("SELECT actual_provider_calls,actual_input_tokens,actual_output_tokens FROM research_budget_ledgers")).one()
        assert tuple(ledger)==(len(provider.calls)+4,len(provider.calls)*100+200,len(provider.calls)*200+80)


def test_research_gate_requires_explicit_native_identity(pg43,tmp_path):
    fixture=make_research(pg43);repository,journal=services(pg43,fixture)
    journal.object_store=Files(tmp_path)
    captured=capture_fixture(repository,fixture)
    gate=make_gate(repository,journal,Provider(summary(fixture,captured.units)),identity=None)
    with pytest.raises(CompactionError,match="native_provider_identity_required"):
        gate.prepare_main_dispatch(fixture.owner,GenerationRequest((),200),captured.units,fixture.policy,
            expected_context_version=0,logical_key="missing-provider")
    with pg43.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM research_provider_calls"))==0
