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
