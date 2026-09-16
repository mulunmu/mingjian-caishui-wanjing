# RAG v2 / Stage 14 Rollout And Rollback

## Verified Candidate

- Git tag: `rag-v2-stage14g-e2e-verified-20260917`
- Commit: `a19d45a`
- Core dependencies: pinned in `backend/requirements.txt`
- LangGraph dependencies: pinned in `backend/requirements-orchestration.txt`

## Feature Switches

Safe defaults:

```text
INSTALL_ORCHESTRATION=false
LANGGRAPH_OUTER_ENABLED=false
LANGGRAPH_REPORT_APPROVAL_REQUIRED=false
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
