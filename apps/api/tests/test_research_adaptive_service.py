"""Exercise supplemental queries through the persisted search service.

The embedding and retrieval backend are deterministic test doubles. These tests
prove query forwarding, scope and ledger enforcement, not search recall quality.
"""
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace as N
from uuid import uuid4
import sys
import pytest
from sqlalchemy import select
from ai_pdf_api.models import (AssetRepresentation, EvidenceLocator, ContentUnit, PdfLocatorDetail,
    ResearchExecutionAsset, ResearchToolCall)
from ai_pdf_api.services.research import research_worker_evidence
from ai_pdf_api.services.retrieval import RetrievedContent
from ai_pdf_api.services.research.research_idempotency import ResearchError
from research_worker_test_support import lease_default_step, sha256
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'worker' / 'src'))
from ai_pdf_worker.research_adaptive_retrieval import research_adaptively


@pytest.mark.parametrize('stop', [None, 'budget', 'cancel'])
def test_supplemental_query_uses_real_search_scope_and_tool_ledger(research_worker_db, monkeypatch, stop):
    f = research_worker_db; db = f.db
    f.snapshot.agent_result_schema_version = "research-agent-results-v2"
    f.snapshot.max_tool_calls = 1 if stop == 'budget' else 4
    rep = AssetRepresentation(id=str(uuid4()), workspace_id=f.run.workspace_id, asset_id=f.asset.id,
        representation_kind='pdf_page_layout', processing_generation=f.asset.current_processing_generation,
        generator_provider='parser', generator_model='parser', generator_version='v1',
        object_key='test-representation', content_sha256=sha256('rep'), created_at=f.now)
    loc = EvidenceLocator(id=str(uuid4()), workspace_id=f.run.workspace_id, asset_id=f.asset.id,
        locator_kind='pdf_page', locator_version=1, processing_generation_snapshot=f.asset.current_processing_generation,
        representation_id_snapshot=rep.id, created_at=f.now)
    unit = ContentUnit(id=str(uuid4()), workspace_id=f.run.workspace_id, asset_id=f.asset.id,
        representation_id=rep.id, source_locator_id=loc.id, unit_kind='pdf_text', unit_order=0,
        text_content='The missing date is 2026.', token_count=8,
        index_version=f.asset.current_index_version, created_at=f.now)
    db.add_all([rep, loc, unit, PdfLocatorDetail(locator_id=loc.id, page_number=1),
        ResearchExecutionAsset(execution_snapshot_id=f.snapshot.id, workspace_id=f.run.workspace_id,
            asset_id=f.asset.id, asset_order=0, asset_kind_snapshot='pdf', asset_title_snapshot='source',
            processing_generation_snapshot=f.asset.current_processing_generation,
            index_version_snapshot=f.asset.current_index_version)])
    db.commit(); lease = lease_default_step(f)
    forwarded = []; embeddings = []; model_calls = []
    class Embedding:
        provider=f.snapshot.embedding_provider; model=f.snapshot.embedding_model; version=f.snapshot.embedding_version
        def embed_query(self, query): embeddings.append(query); return [0.25,0.75]
    def retrieve(session, workspace, query, vector, **kw):
        assert workspace == f.run.workspace_id and kw['asset_ids'] == [f.asset.id]
        assert kw['limit'] == f.snapshot.retrieval_top_k and kw['strategy'] == f.snapshot.retrieval_strategy
        forwarded.append(query)
        return [] if query == 'initial' else [RetrievedContent(content_unit=unit, asset=f.asset,
            locator=loc, channel='text', distance=0.1, location_key=(f.asset.id,'pdf_page:1'))]
    monkeypatch.setattr(research_worker_evidence, 'retrieve_query_content', retrieve)
    class Tools:
        counter=0
        def search(self, *, query, asset_ids, top_k):
            self.counter += 1
            rows = research_worker_evidence.search_frozen_evidence(db,
                run_id=f.run.id, execution_snapshot_id=f.snapshot.id, step_id=f.step.id,
                attempt_id=lease.attempt_id, branch_key=f.step.branch_key, tool_call_key=f'adaptive-search:{self.counter}',
                query=query, asset_ids=asset_ids, top_k=top_k, embedding_provider=Embedding(),
                now=f.now+timedelta(seconds=1))
            return [N(id=row.evidence_handle, **{k:v for k,v in asdict(row).items() if k != 'evidence_handle'}) for row in rows]
        def load(self, *, evidence_handles):
            return [N(evidence_handle=h, content=unit.text_content, asset_id=f.asset.id,
                locator_id=loc.id, content_sha256=sha256(unit.text_content)) for h in evidence_handles]
    def model(_lease, _role, variables):
        model_calls.append(variables)
        if len(model_calls) == 1:
            if stop == 'cancel':
                f.run.status='cancel_requested'; f.run.cancel_requested_at=f.now
                f.run.cancel_requested_by_user_id=f.run.created_by_user_id; f.run.cancel_reason_code='user_requested'; db.commit()
            return {'claims':[], 'nextQuery':'missing date'}
        return {'claims':[{'text':unit.text_content,
            'evidenceHandleIds':[variables['toolContracts']['evidence'][0]['evidenceHandle']]}], 'nextQuery':None}
    def checkpoint(lease, turn, request, result=None):
        from citeframe_research_persistence.adaptive_turns import adaptive_turn
        value = adaptive_turn(db, attempt_id=lease.attempt_id, lease_token=lease.lease_token,
            turn_number=turn, request=request, result=result, now=f.now+timedelta(seconds=1))
        db.commit()
        return value
    def execute():
        return research_adaptively(N(question='initial', asset_ids=(f.asset.id,), branch_key=f.step.branch_key),
            Tools(), lease, top_k=f.snapshot.retrieval_top_k, result_schema={}, generate_json=model, checkpoint=checkpoint)
    if stop:
        with pytest.raises(ResearchError) as caught: execute()
        assert caught.value.code == ('research_budget_limit' if stop == 'budget' else 'research_state_conflict')
        assert embeddings == ['initial'] and forwarded == ['initial']
    else:
        output=execute()
        assert forwarded == embeddings == ['initial','missing date']
        assert output.claims[0].text == unit.text_content
        assert len(output.evidence) == 1
        calls=list(db.scalars(select(ResearchToolCall)))
        assert len(calls) == 2 and all(call.status == 'succeeded' for call in calls)
        db.refresh(f.ledger)
        assert f.ledger.actual_tool_calls == 2 and f.ledger.reserved_tool_calls == 0
