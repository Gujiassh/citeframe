from types import SimpleNamespace as N
import pytest
from ai_pdf_worker.research.adaptive_retrieval import research_adaptively
from ai_pdf_worker.research.schemas import validate_adaptive_agent_result
from citeframe_contracts import ResearchExecutionError


def handle(n, *, excerpt=None):
    return N(id=f'h{n}', asset_id='asset', representation_id='rep', processing_generation=1,
        index_version=2, parser_version='parser', excerpt=excerpt or f'evidence{n}')

class Tools:
    def __init__(self, results):
        self.results = results; self.queries = []; self.loads = []
    def search(self, *, query, asset_ids, top_k):
        assert asset_ids == ('asset',) and top_k == 4
        self.queries.append(query)
        return self.results[len(self.queries)-1]
    def load(self, *, evidence_handles):
        self.loads.append(evidence_handles)
        return [N(evidence_handle=h, content='text', asset_id='asset', locator_id='locator', content_sha256='a'*64) for h in evidence_handles]


def run(tools, outputs):
    calls = []
    def generate(lease, role, variables):
        calls.append(variables)
        value = outputs[len(calls)-1]
        validate_adaptive_agent_result(role, value)
        return value
    result = research_adaptively(N(question='initial', asset_ids=('asset',), branch_key='branch'),
        tools, N(step_id="step"), top_k=4, result_schema={}, generate_json=generate, checkpoint=lambda *args: None)
    return result, calls


def result(query, ids=('h1',)):
    return {'claims': [{'text':'fact', 'evidenceHandleIds':list(ids)}] if ids else [], 'nextQuery':query}


def test_missing_information_query_is_chosen_by_model_and_scoped():
    tools = Tools([[], [handle(1)]])
    answer, calls = run(tools, [result('missing date', ()), result(None)])
    assert tools.queries == ['initial', 'missing date']
    assert tools.loads == [('h1',)]
    assert [v['toolContracts']['remainingSearches'] for v in calls] == [2,1]
    assert answer.claims[0].evidence_handle_ids == ('h1',)


def test_hard_round_limit_even_when_model_keeps_requesting_queries():
    tools = Tools([[handle(1)], [handle(2)], [handle(3)]])
    answer, calls = run(tools, [result('q2'), result('q3'), result('q4')])
    assert tools.queries == ['initial','q2','q3'] and len(calls) == 3
    assert calls[-1]['toolContracts']['remainingSearches'] == 0
    assert len(answer.evidence) == 3


def test_duplicate_query_stops_before_another_tool_call():
    tools = Tools([[handle(1)]])
    _, calls = run(tools, [result(' INITIAL  ')])
    assert len(calls) == 1 and tools.queries == ['initial']


def test_duplicate_content_with_new_snapshot_ids_stops_without_extra_model_call():
    tools = Tools([[handle(1)], [handle(2, excerpt='evidence1')]])
    answer, calls = run(tools, [result('new query')])
    assert len(calls) == 1 and tools.loads == [('h1',)]
    assert [e.id for e in answer.evidence] == ['h1']


def test_no_results_terminates_with_no_fabricated_claim():
    answer, calls = run(Tools([[], []]), [result('more', ())])
    assert not answer.claims and not answer.evidence and len(calls) == 1


def test_model_cannot_supply_an_unissued_evidence_handle():
    with pytest.raises(ResearchExecutionError):
        run(Tools([[handle(1)]]), [result(None, ('foreign',))])


@pytest.mark.parametrize('payload',[{'claims':[], 'nextQuery':'', 'assetIds':['foreign']},
    {'claims':[], 'nextQuery':'x'*1001}, {'claims':[], 'nextQuery':None, 'tool':'browser'},
    {'claims':[], 'nextQuery':42}])
def test_closed_model_contract_rejects_tool_or_scope_escalation(payload):
    with pytest.raises(ValueError): validate_adaptive_agent_result('researcher',payload)


def test_budget_or_cancel_failure_is_not_swallowed_or_retried():
    tools = Tools([[handle(1)]])
    def stopped(**kwargs): raise ResearchExecutionError('research_budget_limit')
    tools.search = stopped
    with pytest.raises(ResearchExecutionError, match='research_budget_limit'):
        run(tools, [result(None)])


def test_later_empty_turn_preserves_previously_evidenced_claims():
    answer, _ = run(Tools([[handle(1)], [handle(2)]]), [result('missing date'), result(None, ())])
    assert len(answer.claims) == 1 and answer.claims[0].evidence_handle_ids == ('h1',)


def test_repeated_claim_is_deduplicated_across_turns():
    answer, _ = run(Tools([[handle(1)], [handle(2)]]), [result('missing date'), result(None)])
    assert len(answer.claims) == 1
