# Mingjian Semantic RAG V2 Implementation Plan

> Status is updated only after the stated verification passes.

## Goal

Replace patch-based routing with a versioned semantic registry, structured Tool
RAG, deterministic planning, topic-thread memory, and blueprint-based report
generation while preserving the numeric truth boundary.

## Stages

### Stage 0: Baseline And Isolation

- [x] Confirm repository state and current failures.
- [x] Establish validation harness and evidence report.
- [x] Confirm one-off validation containers are removed.

Verification:

- Current full backend baseline remains 11 pre-existing failures.
- Validation harness core tests passed before implementation began.

### Stage 1: Metric Catalog Audit

- [x] Add executable metric-catalog audit.
- [x] Identify all core fields missing from canonical tools.
- [x] Define the P0 metric tranche.
- [x] Add tests for audit completeness and P0 metadata.

Deliverables:

- `backend/scripts/audit_metric_catalog.py`
- `backend/tests/test_metric_catalog_audit.py`
- `报告/Metric-Catalog-v2-Audit.md`

Verification:

```text
3 passed
core_columns=55
canonical_metrics=22
source_fields=36
p0_candidates=66
```

### Stage 2: Registry Schema

- [x] Extend metric definitions with version, status, category, and retrieval metadata.
- [x] Add threshold rules.
- [x] Add tool definitions, aliases, dependencies, and examples.
- [x] Add topic-thread persistence structures.
- [x] Add idempotent migrations for existing PostgreSQL installations.

Verification gate:

- [x] Migration tests on an existing PostgreSQL schema.
- [x] New tables and columns created idempotently.
- [x] Existing chat/session tests remain unchanged.

Verification evidence:

```text
5 registry/audit tests passed
2 PostgreSQL migration integration tests passed
Full backend suite: 1083 passed, 8 skipped, 11 pre-existing failures
Failure set unchanged from Stage 0 baseline
```

### Stage 3: P0 Metric Seed

- [x] Seed implemented P0 atomic metrics.
- [x] Seed threshold-rule baselines.
- [x] Seed scenario and chapter tools.
- [x] Mark uncomputed metrics as planned and exclude them from retrieval.

Verification gate:

- [x] Every seeded metric has formula, source, aliases, grain, and version.
- [x] Planned tools have `enabled=false` and `status=planned`.

Seeded totals:

```text
metrics=84
tools=92
aliases=184
thresholds=16
```

Verification evidence:

```text
8 stage-specific tests passed
3 PostgreSQL migration/seed integration tests passed
Full backend suite: 1097 passed, 9 skipped, 0 failed
```

### Stage 4: Backend Tool RAG

- [x] Port structured catalog and retrieval into backend services.
- [x] Add BM25/vector-compatible metadata contract.
- [x] Add route normalization and question-filler normalization.
- [x] Add multilingual aliases.

Verification gate:

- [x] Human-authored retrieval set reaches Recall@5 >= 90%.
- [x] No unknown tool IDs may pass validation.

Verification evidence:

```text
64 human-authored queries
Recall@5=100%
planned tools excluded from retrieval
Registry seed: metrics=100 tools=108 aliases=303 thresholds=16
13 stage-specific tests passed
Full backend suite: 1104 passed, 9 skipped, 0 failed
```

### Stage 5: Conversation Policy And Topic Memory

- [x] Integrate route policy into a shadow dialogue path.
- [x] Add topic-thread storage and N-1/N-2/semantic back-reference.
- [x] Add candidate-retrieval versus execution separation.
- [x] Keep `chat_router` as fallback until shadow results pass.

Verification gate:

- [x] Non-analysis routing matrix passes.
- [x] Multi-topic rollback and cross-topic follow-up pass.

Verification evidence:

```text
11 stage-specific tests passed
4 PostgreSQL migration/topic integration tests passed
Full backend suite: 1115 passed, 10 skipped, 0 failed
```

### Stage 6: Plan Validation And Execution

- [x] Add typed tool plans.
- [x] Add DAG validation, cycle detection, and dependency checks.
- [x] Execute plans only through deterministic backend tools.

Verification gate:

- [x] Invalid plans never execute.
- [x] Repeated execution yields identical claims.

Verification evidence:

```text
7 stage-specific tests passed
5 PostgreSQL migration/topic/plan integration tests passed
Full backend suite: 1122 passed, 10 skipped, 0 failed
```

### Stage 7: Report Blueprint

- [x] Add section, block, and blueprint schemas.
- [x] Compile blueprints into chapter tool DAGs.
- [x] Prevent whole-report LLM generation.
- [x] Persist and re-run blueprints.

Verification gate:

- [x] Repeated blueprint execution is deterministic.
- [x] Claims do not leak across chapters.

Verification evidence:

```text
5 Blueprint unit tests passed
6 PostgreSQL migration/topic/plan/blueprint tests passed
Full backend suite: 1127 passed, 12 skipped, 0 failed
```

### Stage 8: Shadow Integration

- [x] Run old and new dialogue paths side by side.
- [x] Compare route, tool, latency, and answer coverage.
- [x] Switch traffic only after gates pass.

Verification gate:

- [x] No reduction in current successful behavior.
- [x] Baseline failure count does not increase.

Verification evidence:

```text
8 shadow hook/integration tests passed
7 PostgreSQL migration/topic/plan/blueprint/shadow integration tests passed
Full backend suite: 1135 passed, 13 skipped, 0 failed
```

Production integration remains default-off via `SHADOW_SEMANTIC_ENABLED=false`.
The shadow hook runs only after the legacy response succeeds, and all shadow
errors are swallowed without changing the legacy response.

### Stage 8.5: Deployment Preparation

- [x] Pass `SHADOW_SEMANTIC_ENABLED` through Docker Compose.
- [x] Add idempotent readiness command.
- [x] Add shadow-evaluation summary command.
- [x] Add deployment, rollback, and evaluation runbook.
- [x] Verify the complete pre-production migration and seed flow on PostgreSQL.

Verification evidence:

```text
9 required tables present
validated_metrics=52
validated_tools=60
validated_thresholds=14
planned_enabled_tools=[]
seed: metrics=100 tools=108 aliases=305 thresholds=16
```

### Stage 9A: Retirement Preflight Audit

- [x] Add executable legacy-retirement scanner.
- [x] Audit old entrypoint, regex fallback, and chapter compatibility aliases.
- [x] Replace redline v1 with redline v2.
- [x] Archive redline v1.
- [x] Confirm legacy removal is blocked until the shadow gate passes.
- [x] Make pre-release shadow route independent from the legacy result.

Verification evidence:

```text
12 independent-route/shadow tests passed
3 legacy-retirement audit tests passed
safe_to_retire=false
blockers=shadow_gate_not_passed, legacy_markers_remain, legacy_entrypoint_still_active, chapter_compatibility_still_imported
Full backend suite: 1164 passed, 13 skipped, 0 failed
```

### Stage 9B: Combined Release Gate

- [x] Combine semantic readiness and shadow evidence into one decision.
- [x] Add `stay_on_legacy` and `ready_for_canary` decisions.
- [x] Add executable deployment gate CLI.
- [x] Verify fresh PostgreSQL remains blocked without shadow samples.

Verification evidence:

```text
3 deployment-gate tests passed
fresh PostgreSQL decision=stay_on_legacy
```

### Stage 9C: Semantic Execution Registry

- [x] Add asynchronous ToolPlan execution.
- [x] Register supported validated metrics with deterministic `judgment_service`.
- [x] Extend numeric core-field mapping for executor coverage.
- [x] Add executable-only Tool RAG filtering.
- [x] Prevent canary plans from selecting validated tools without executors.

Verification evidence:

```text
15 executor/async-plan/Tool-RAG tests passed
```

### Stage 9D: Semantic Answer Composer

- [x] Compose independent route, candidate retrieval, plan, execution, narration, and guard.
- [x] Add executable-only candidate selection.
- [x] Add display-name to enterprise-ID resolution.
- [x] Add clarify and abstain outcomes.
- [x] Keep the composer disconnected from production traffic by default.

Verification evidence:

```text
6 semantic-answer-composer tests passed
```

### Stage 9E: Shadow Answer Observation

- [x] Evaluate the semantic answer composer in shadow mode.
- [x] Store privacy-minimized answer-level observations.
- [x] Add answer success, reply presence, error, claim-count, and latency gates.
- [x] Include answer evidence in the combined release gate.
- [x] Keep answer evaluation disabled by default.

Verification evidence:

```text
3 shadow-answer tests passed
12 shadow-answer/gate/deployment tests passed
```

### Stage 9F: Pre-Release Evaluation

- [x] Restore anonymized PostgreSQL data into an isolated staging project.
- [x] Run readiness migration and Registry seed.
- [x] Enable independent shadow routing and answer evaluation.
- [x] Generate 30 staging observations.
- [x] Resolve weak-route mismatches with Tool RAG evidence.
- [x] Pass the combined release gate.

Verification evidence:

```text
samples=30
route_match_rate=1.0000
domain_match_rate=1.0000
avg_tool_coverage=1.0000
switch_eligible_rate=1.0000
answer_rate=1.0000
reply_present_rate=1.0000
error_rate=0.0000
decision=ready_for_canary
Full backend suite: 1169 passed, 13 skipped, 0 failed
```

### Stage 9G: Canary Activation And Dormant Rollback

- [x] Route a deterministic percentage of real staging traffic to the semantic composer.
- [x] Replace the legacy reply only after the semantic turn is answered.
- [x] Persist the replacement through the session history before returning it.
- [x] Fall back to legacy on route, composition, configuration, or persistence failure.
- [x] Keep canary disabled by default with `SEMANTIC_CANARY_PERCENT=0`.
- [x] Run an HTTP-level staging drill and restore the dormant configuration.

Verification evidence:

```text
targeted canary/session tests=17 passed
full backend suite=1177 passed, 13 skipped, 0 failed
live staging cases=7
analysis canary status=answered
analysis reply source=llm
analysis history match=true
non-analysis cases=6, http errors=0
dormant check: canary_present=false, reply_source=template
SEMANTIC_CANARY_PERCENT restored to 0
```

### Stage 9: Retirement And Cleanup

- [x] Remove unreferenced chapter compatibility aliases.
- [x] Keep only compatibility paths that remain active on the legacy chain.
- [x] Add an executable retirement-audit CLI.
- [x] Update redline v2 and operational documentation.
- [x] Retire `route_chat` and soft-fallback regexes from the active application.
- [x] Make the active chat endpoint fail closed instead of silently falling back to legacy.
- [x] Restore fixed and conversational report generation in the semantic-primary path.
- [x] Re-run the retirement audit until `safe_to_retire=true`.
- [x] Exclude the archived `backend/legacy` package from production images.

Verification gate:

- [x] Full backend suite passes or every remaining failure is explicitly accepted.
- [x] End-to-end chat and report path verified on anonymized data.

Verification evidence:

```text
chapter compatibility aliases=0
all chapter keys map to loan|rating|warn|audit
invalid wizard scenario -> HTTP 422
full backend suite=1259 passed, 7 skipped, 0 failed
production semantic-primary matrix=32/32, fallback_count=0
multi-topic memory=6 turns, N-2 reply resolved
production report chat=answered, PDF magic=%PDF-
active-app legacy imports=0
production image legacy package=absent
safe_to_retire=true
remaining blockers=none
```

The active application no longer imports or calls the legacy package. Legacy source remains
only as a repository archive for historical tests/offline scripts and is excluded from the
production image; it is not part of the runtime response path.
