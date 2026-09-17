# RAG v2 / Stage 14 Rollout And Rollback

## Verified Candidate

- Git tag: `rag-v2-stage16-accepted-20260917`
- Core dependencies: pinned in `backend/requirements.txt`
- LangGraph dependencies: pinned in `backend/requirements-orchestration.txt`

## Feature Switches

Safe defaults:

```text
INSTALL_ORCHESTRATION=true
LANGGRAPH_OUTER_ENABLED=true
LANGGRAPH_REPORT_APPROVAL_REQUIRED=true
REPORT_BLOCK_TREE_ENABLED=true
SEMANTIC_PRIMARY_ENABLED=true
SEMANTIC_PRIMARY_PERCENT=100
SHADOW_SEMANTIC_ENABLED=false
SHADOW_ANSWER_EVAL_ENABLED=false
```

`SEMANTIC_PRIMARY_ENABLED=false` makes chat fail closed with 503. It is not a
rollback to legacy because the legacy entry point has been removed. Production
rollback for a primary-path defect is redeployment of the previous accepted
image/tag, not disabling primary in place.

## Promotion

1. Build the canary image with `INSTALL_ORCHESTRATION=true` only when testing the
   outer state machine.
2. Start a temporary backend against staging data and run:
   `python -m scripts.verify_semantic_readiness --apply`
   `python -m scripts.audit_module_coverage --strict`
   `python -m scripts.run_stage14_report_block_matrix`
3. Run `python -m scripts.run_stage12_dialogue_quality --base-url ... --json`.
4. Run `python -m scripts.run_staging_composition_matrix` with
   `STAGING_CONFIRM=true`.
5. Run the canary smoke and the full backend regression.
6. Promote the exact image that passed all gates. Do not rebuild from a moving
   dependency range.

## Rollback

### Outer Orchestrator

Set either:

```text
INSTALL_ORCHESTRATION=false
LANGGRAPH_OUTER_ENABLED=false
```

Then redeploy the core image. Primary dialogue and report generation do not
depend on LangGraph.

The verified pre-LangGraph rollback image is tagged locally as
`20-backend-pre-langgraph-20260917`.

### Report Block Tree

Set:

```text
REPORT_BLOCK_TREE_ENABLED=false
```

This restores legacy metric/synthesis paragraph generation. Existing snapshots
keep their persisted `block_tree_version`, so historical reports remain
readable.

### Semantic Primary Defect

Do not disable `SEMANTIC_PRIMARY_ENABLED` and expect legacy behavior. Roll back
to the previous image/tag:

```text
rag-v2-stage14g-e2e-verified-20260917
rag-v2-stage14f-report-blocks-20260917
rag-v2-stage12a-block-reports-20260917
```

The database migrations are additive and must not be dropped during rollback.
Keep `conversation_topic` memory columns, report snapshots and LangGraph
checkpoint tables in place.

## Observability

Sentry has not been configured because no auth token was provided. Do not claim
Sentry coverage. Use application logs and the readiness/audit scripts until
Sentry credentials and deployment wiring are supplied.

## Stage 16 LLM Runtime Contract

Production model settings:

```text
LLM_DIALOGUE_MODEL=deepseek-v4-flash
LLM_MODEL=deepseek-v4-pro
LLM_TIMEOUT_SECONDS=15
LLM_DAILY_LIMIT=1000
```

Core dialogue generation is fail-closed:

1. Classify with one non-blocking `instructor` call using the fast model.
2. Author the answer with one fast async JSON call.
3. If the fast authoring call fails, enter the schema-constrained pro path.
4. If both calls fail, return the controlled 503 path. Never replace the core
   answer with a fixed template or raw Claim text.

Classification and the common authoring path disable provider and Instructor
retries. The pro repair path permits at most one explicit Instructor
schema-repair retry after an empty or malformed conclusion list. Fenced JSON and
JSON wrapped by prose are parsed locally before any model escalation.

## Stage 16 Lifecycle And Evidence

Report approval interrupts expire after `LANGGRAPH_APPROVAL_TTL_SECONDS=900` by
default. A stale interrupt must not hijack a new unrelated question.

Checkpoint cleanup is dry-run by default:

```text
python -m scripts.cleanup_langgraph_checkpoints --days 7
python -m scripts.cleanup_langgraph_checkpoints --days 7 --apply
```

Stage 16 production evidence:

```text
105-case matrix run A: 105/105, P50 1392.40ms, P95 6593.86ms
105-case matrix run B: 105/105, P50 1217.37ms, P95 6250.07ms
targeted repeated probe: 30/30 successful
full backend regression: 800 passed, 8 skipped (test auth contract)
frontend production build: passed
Sentry SDK installed; SENTRY_DSN not configured; no Sentry events claimed
```

## Stage 17 Metric And Threshold Closure

Stage 17 classifies every previous `planned` metric into one of two terminal
states:

- `validated`: a deterministic executor exists and the metric can enter RAG.
- `unsupported`: the required source fields or time series do not exist; the
  metric remains disabled and must never enter RAG.

Current registry state:

```text
registry_metrics_total=103
metrics_validated=67
metrics_unsupported=36
metrics_planned=0
validated_thresholds=16
planned_thresholds=0
```

Validated Stage 17 additions:

```text
cross_avg_deviation
cross_max_deviation
customer_count
customer_hhi
customer_top5_concentration
income_tax_effective_rate
invalid_invoice_ratio
ocf_to_revenue
red_invoice_count_ratio
supplier_count
supplier_hhi
supplier_top5_concentration
violation_recency_days
void_invoice_ratio
```

Unsupported examples and reasons are stored in `metric_definition.edge_cases`.
They include missing time series, missing tax amounts, missing employee count,
missing registered capital, and scenario composites whose required inputs are
not yet complete. Unsupported tools have `enabled=false` and
`retrieval_enabled=false`.

Required Stage 17 gates:

```text
python -m scripts.audit_stage17_metric_data
python -m scripts.audit_module_coverage --strict
python -m scripts.verify_semantic_readiness --apply
```

Promotion of an unsupported metric is allowed only after adding the missing
source field, a deterministic executor, boundary tests, aliases, and a passing
strict audit. Do not turn it back into `planned`; move it directly to
`validated`.

## Stage 18 Hybrid RAG

PostgreSQL runs from the `pgvector/pgvector:pg16` image with the `vector`
extension. Validated tools have one versioned embedding row in
`semantic_embedding` using:

```text
model=BAAI/bge-small-zh-v1.5
dimension=512
index=ix_semantic_embedding_hnsw
```

Runtime switches:

```text
RAG_HYBRID_ENABLED=true
RAG_EMBEDDINGS_AUTO_SEED=true
RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_EMBEDDING_DIM=512
HF_ENDPOINT=https://hf-mirror.com
HF_HUB_DISABLE_XET=1
```

Retrieval order is:

```text
validated snapshot
-> pgvector dense cosine candidates
-> BM25 lexical candidates
-> exact/title/alias/domain rules
-> reciprocal-rank fusion
-> executable-only filter
```

If embeddings or pgvector are unavailable, retrieval falls back to the
deterministic lexical retriever. Rollback without removing data:

```text
RAG_HYBRID_ENABLED=false
```

Stage 18 gates:

```text
python -m scripts.rebuild_tool_embeddings --force
python -m scripts.audit_stage18_hybrid_retrieval --json
python -m scripts.verify_semantic_readiness --apply
```

The current golden set has 77 queries. Required gates are Recall@5 >= 0.90,
dense coverage >= 0.90, and unsupported leakage = 0.

## Stage 19 Long Memory And Agent Closure

Long-memory switches:

```text
MEMORY_SEMANTIC_ENABLED=true
LANGGRAPH_FINANCE_REVIEW_ENABLED=false
LANGGRAPH_FINAL_GUARD_ENABLED=true
LANGGRAPH_AGENT_BUDGET_MS=15000
```

Memory behavior:

```text
durable ConversationTopic
-> ordered ordinal references for N-1/N-2/absolute turn
-> semantic and bigram content reference matching
-> recent-first de-duplicated summary compression
-> correction detection without silently changing the current topic
```

The outer memory Agent result is passed directly into the semantic primary
executor, avoiding duplicate topic retrieval in the same turn.

Agent behavior:

```text
memory -> classification -> planning -> approval
-> execution -> finance_review -> final_guard -> verification
```

- `finance_review_agent` is skipped when the financial model is absent.
- `final_guard_agent` rejects empty replies, fallback responses and untraceable Claims.
- The execution-to-review budget is bounded by `LANGGRAPH_AGENT_BUDGET_MS`.
- Finance review can add causal interpretation metadata but cannot own numbers or final facts.

Stage 19 gates:

```text
python -m scripts.run_stage19_long_dialogue --json
python -m scripts.verify_semantic_readiness --apply
python -m scripts.audit_module_coverage --strict
```

The long-dialogue gate requires four 40-turn conversations covering correction,
content back-reference, N-2 rollback and unrelated intervening turns.

## Stage 20 Financial Model

Financial model configuration resolution:

```text
FINANCIAL_LLM_MODEL / FINANCIAL_LLM_API_KEY / FINANCIAL_LLM_BASE_URL
-> fallback to LLM_MODEL / LLM_API_KEY / LLM_BASE_URL for API baseline only
```

Default runtime:

```text
LANGGRAPH_FINANCE_REVIEW_ENABLED=false
```

The finance review Agent is optional. It may only reinterpret existing Claims,
cannot emit digits, and cannot modify final facts or the main reply.

API baseline evidence:

```text
model=deepseek-v4-pro
source=main_api_baseline
passed=10/10
digit_leakage=0
P50=4996.26ms
P95=8945.87ms
```

The latency result fails the every-turn gate, so finance review remains disabled
for normal dialogue. It may be used for asynchronous report review or after a
lower-latency local model is validated.

Local deployment gate:

```text
current GPU=RTX 4060 Laptop 8GB
current RAM=16GB
DISC-FinLLM 13B production deployment=not approved
XuanYuan-6B-Chat-4bit production deployment=not approved; PoC only
recommended production hardware>=24GB VRAM and >=32GB RAM
```

Evaluation commands:

```text
python -m scripts.evaluate_financial_model --json
python -m scripts.verify_semantic_readiness --apply
```

## Stage 21 Report Block Editor

Report snapshots use `block_tree_version=2`. Each active paragraph block stores:

```text
block_id
version
content_hash
status
locked
source_claim_index
```

Mutation endpoints:

```text
GET   /api/v1/report/{report_id}/blocks
PATCH /api/v1/report/{report_id}/blocks/{block_id}
POST  /api/v1/report/{report_id}/blocks/{block_id}/regenerate
POST  /api/v1/report/{report_id}/blocks/{block_id}/restore
```

Supported actions are lock/unlock, reorder, soft-delete and restore. Regeneration
can only rebuild from the original Claim index; the API never accepts arbitrary
paragraph text. Locked blocks cannot be regenerated, moved or removed.

Snapshots embed chart assets as data URIs before removing filesystem paths so
block edits can re-render PDF without losing charts. API, HTML and PDF render the
same active blocks in the same order; removed blocks remain in revision history
but are not rendered.
