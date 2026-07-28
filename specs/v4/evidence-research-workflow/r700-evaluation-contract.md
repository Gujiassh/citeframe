# R700 Evaluation Persistence/API Contract

## 1. Status and authority

- Status: approved implementation input for R700.
- Date: 2026-07-27.
- Authority: Owner authorized autonomous implementation of all recommended remaining V4 stages with no further per-stage approval.
- Boundary: this contract is independent from the immutable R000 contracts. It must not add an Evaluation Step/Event to the Research DAG, modify a ResearchRun, or reinterpret a ResearchArtifact as an Evaluation record.

## 2. Product decision

R700 is an internal owner-facing engineering dashboard, not an end-user quality claim and not a browser-triggered model runner. A trusted offline evaluator imports immutable reports after validating the fixture manifest and source artifacts. The Web surface is read-only.

The smallest complete scope is:

1. immutable versioned suites;
2. append-only evaluation runs with case and claim results;
3. explicit Quick/Research pairing only when comparison keys match;
4. owner-only list/detail APIs and dashboard;
5. strict separation of engineering, model-quality, and user-value evidence.

## 3. Approved decisions

| ID | Decision |
| --- | --- |
| E001 | Browser/API reads are owner-only. Members and cross-Workspace callers cannot enumerate evaluation metadata. |
| E002 | Browser routes never launch an evaluation. Import is an internal CLI/service operation using a validated report file and canonical hashes. |
| E003 | Suites, runs, cases, and claims are append-only. A correction creates a new evaluator version/run; published rows are never rewritten. |
| E004 | A Quick/Research pair is comparable only when suite version, fixture manifest hash, case set, Asset-scope hash, provider/model profile, and scorer version match. Workflow/Prompt versions remain comparison dimensions, not hidden coercions. |
| E005 | `engineering`, `model_quality`, and `user_value` gates are independent closed enums. Scripted/provider-free evidence cannot pass model quality. User value remains `not_evaluable` until an M404 evidence reference is attached. |
| E006 | Persisted rows and public DTOs exclude prompt text, chain of thought, raw provider/tool payloads, secrets, object keys, and user-auth data. Claim rows use fixture claim IDs and result codes; sensitive source text remains in already governed artifacts. |
| E007 | R700 uses dedicated tables, schemas, router, service, and Web client. It does not modify the R000 state machine, 15-event SSE allowlist, or Quick Chat contract. |

## 4. Persistence model

### 4.1 `research_evaluation_suites`

- `id`, UUID text primary key
- `suite_key`, stable non-secret key
- `version`, positive integer
- `title`, bounded display text
- `fixture_manifest_sha256`, lowercase SHA-256
- `scorer_version`, immutable version string
- `case_count`, non-negative integer
- `created_at`
- unique `(suite_key, version)` and `(fixture_manifest_sha256, scorer_version)`

### 4.2 `research_evaluation_runs`

- `id`, `workspace_id`, `suite_id`
- `mode`: `quick | research`
- `status`: `not_evaluable | completed | failed`
- `research_run_id`, nullable and only valid for `mode=research`
- `baseline_evaluation_run_id`, nullable self-reference and only valid for `mode=research`
- comparison keys: `fixture_manifest_sha256`, `asset_scope_sha256`, `provider`, `model`, `provider_profile_sha256`, `scorer_version`
- version dimensions: nullable `workflow_version_id`, `prompt_binding_sha256`
- source integrity: `source_report_sha256`, nullable `source_artifact_sha256`
- engineering facts: `wall_time_ms`, `provider_calls`, `input_tokens`, `output_tokens`, `cost_currency`, `cost_microunits`, `parallel_speedup`, `retry_rate`, `recovery_rate`
- aggregate ratios: claim support, evidence recall/precision, locator accuracy, conflict detection, refusal correctness; every ratio stores `value`, `sample_count`, and nullable `not_evaluable_reason`
- gates: `engineering_gate`, `model_quality_gate`, `user_value_gate`, each `not_evaluable | pass | fail`
- nullable safe failure code/message, `created_at`, `completed_at`
- unique `(workspace_id, source_report_sha256)`

### 4.3 `research_evaluation_case_results`

- `id`, `evaluation_run_id`, `case_key`, `case_type`
- expected/observed disposition: `answer | refuse | not_evaluable`
- per-case ratio metrics and engineering measurements
- `unsupported_claim_count`, `human_intervention_count`, `human_wait_ms`
- nullable safe failure code; unique `(evaluation_run_id, case_key)`

### 4.4 `research_evaluation_claim_results`

- `id`, `case_result_id`, `claim_key`
- `support_result`: `supported | unsupported | not_evaluable`
- `locator_result`: `accurate | inaccurate | not_evaluable`
- `conflict_result`: `none | detected | missed | not_evaluable`
- expected/observed Evidence counts and closed `failure_code`
- unique `(case_result_id, claim_key)`

## 5. Import contract

The internal importer accepts one canonical JSON report. It validates exact schema fields, suite/fixture/scorer hashes, unique case/claim keys, ratio ranges and sample counts, gate rules, non-negative usage, Workspace/ResearchRun ownership, source Artifact hash, and optional baseline comparison keys before one transaction inserts the complete suite/run/case/claim graph.

Idempotency is `(workspace_id, source_report_sha256)`. Same bytes return the existing evaluation; different bytes always create a new immutable run. Partial imports roll back.

## 6. Read API

All endpoints require current Workspace owner membership and use `cache: no-store` through the BFF.

- `GET /v1/workspaces/{workspaceId}/evaluation-suites`
- `GET /v1/workspaces/{workspaceId}/evaluation-suites/{suiteId}`
- `GET /v1/workspaces/{workspaceId}/evaluations?suiteId=&mode=&cursor=&limit=`
- `GET /v1/workspaces/{workspaceId}/evaluations/{evaluationRunId}`
- `GET /v1/workspaces/{workspaceId}/evaluations/{evaluationRunId}/cases`
- `GET /v1/workspaces/{workspaceId}/evaluations/{evaluationRunId}/cases/{caseKey}`

List results contain aggregate metrics, gates, comparison/version keys, and baseline ID. Case detail contains claim result rows. No endpoint returns raw evaluator input, prompts, provider payloads, or object-storage identity.

## 7. Dashboard contract

The owner dashboard provides suite/run selection, explicit Quick versus Research comparison, Workflow/Prompt version labels, aggregate quality/latency/cost/retry/recovery views, case drill-down, and claim failure rows. It must visibly keep the three evidence gates separate and must render `not_evaluable` without substituting zero or pass.

The dashboard lives outside the primary Chat/Research run flow. It does not add explanatory marketing sections, auto-start evaluation, or imply that an engineering fixture proves real-model quality or user value.

## 8. Acceptance oracles

1. migration upgrade/downgrade and dump/restore preserve every evaluation row and hash;
2. importer replay creates no duplicate rows and malformed reports create none;
3. cross-Workspace and non-owner reads fail without enumeration;
4. mismatched comparison keys cannot be paired;
5. scripted evidence forces `model_quality=not_evaluable`; absent M404 evidence forces `user_value=not_evaluable`;
6. API DTOs contain no forbidden raw fields;
7. dashboard handles pass/fail/not-evaluable, empty suites, and desktop/mobile without overlap;
8. R000 contract hashes and the exact 15 Research SSE events remain unchanged.
