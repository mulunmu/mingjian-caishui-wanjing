# Composition Kernel Implementation Plan

> Execution status 2026-09-16: Tasks 1-5 are implemented. Multi-metric composition
> executes through per-node async sessions and the DAG runtime. Dynamic pattern
> selection, node caching, cache idempotency keys, partial-result execution, report
> chapter concurrency, conditional node execution, turn budgets, and the 30-case
> staging matrix are implemented and verified. Persistent composition Blueprint storage,
> registry-version validation, replay validation, durable execution checkpoints, and
> compatible plan migration are implemented. Migration approval records and the
> composition readiness gate are implemented. The final production retirement audit
> remains pending. Task 6 is not complete.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add typed module composition and an asynchronous DAG runtime that can generate, validate, and execute many dialogue and report combinations without enumerating them.

**Architecture:** Keep the existing policy router as the safety layer. Add a semantic frame, typed module registry, deterministic composition planner, plan validator, and async DAG runtime. Execute independent nodes concurrently with bounded resources and preserve the existing Claims truth boundary.

**Tech Stack:** Python 3.12, asyncio, Pydantic, SQLAlchemy, pytest, existing Tool RAG and semantic registry.

---

## Task 1: Composition IR And Validator

**Files:**
- Create: `backend/app/schemas/composition.py`
- Create: `backend/app/services/composition_validator.py`
- Test: `backend/tests/test_composition_validator.py`

- [ ] **Step 1: Write failing IR and validation tests**

```python
def test_validator_rejects_type_mismatch():
    plan = CompositionPlan(nodes=[...])
    report = validate_composition_plan(plan, modules={...})
    assert report.valid is False
    assert report.errors[0].code == "port_type_mismatch"


def test_validator_accepts_dag_with_parallel_nodes():
    report = validate_composition_plan(plan, modules={...})
    assert report.valid is True
    assert report.topological_order
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest -q tests/test_composition_validator.py`
Expected: FAIL because the schemas and validator do not exist.

- [ ] **Step 3: Implement typed IR**

Add `PortSpec`, `ModuleSpec`, `CompositionBinding`, `CompositionNode`,
`CompositionEdge`, `CompositionPlan`, `CompositionValidationError`, and
`CompositionValidationReport` with Pydantic.

- [ ] **Step 4: Implement deterministic validation**

Validate missing modules, required inputs, type compatibility, duplicate node IDs,
unknown dependencies, cycles, disabled modules, permissions, and node limits.

- [ ] **Step 5: Verify GREEN and commit**

Run: `python -m pytest -q tests/test_composition_validator.py`

```bash
git add backend/app/schemas/composition.py backend/app/services/composition_validator.py backend/tests/test_composition_validator.py
git commit -m "feat: add composition ir and validator"
```

## Task 2: Async DAG Runtime

**Files:**
- Create: `backend/app/services/async_dag_runtime.py`
- Test: `backend/tests/test_async_dag_runtime.py`

- [ ] **Step 1: Write failing runtime tests**

```python
@pytest.mark.asyncio
async def test_independent_nodes_run_concurrently():
    runtime = AsyncDagRuntime(max_concurrency=4)
    report = await runtime.execute(plan, handlers={"a": delay_a, "b": delay_b})
    assert report.elapsed_ms < 180


@pytest.mark.asyncio
async def test_dependent_node_waits_for_input():
    report = await runtime.execute(plan, handlers={...})
    assert report.node_results["b"].inputs["value"] == 1


@pytest.mark.asyncio
async def test_timeout_cancels_node():
    with pytest.raises(NodeTimeoutError):
        await runtime.execute(plan, handlers={"slow": never})
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest -q tests/test_async_dag_runtime.py`
Expected: FAIL because the runtime does not exist.

- [ ] **Step 3: Implement the async executor**

The executor must:

- run ready nodes with `asyncio.TaskGroup`,
- use `asyncio.Semaphore` for bounded concurrency,
- enforce per-node timeouts,
- support retry and fallback,
- bind dependency outputs into node inputs,
- return ordered node results and timings,
- cancel remaining tasks on fatal failure.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest -q tests/test_async_dag_runtime.py tests/test_composition_validator.py`

```bash
git add backend/app/services/async_dag_runtime.py backend/tests/test_async_dag_runtime.py
git commit -m "feat: add async dag runtime"
```

## Task 3: Composition Planner And Patterns

**Files:**
- Create: `backend/app/services/composition_planner.py`
- Create: `backend/app/services/composition_patterns.py`
- Test: `backend/tests/test_composition_planner.py`

- [ ] **Step 1: Write failing planner tests**

```python
def test_planner_builds_metric_threshold_comparison_plan():
    plan = build_composition_plan(frame, candidates, pattern="metric_threshold_compare")
    report = validate_composition_plan(plan, modules)
    assert report.valid is True
    assert {node.module_id for node in plan.nodes} == {
        "metric_debt_ratio", "threshold_debt_ratio", "operator_compare_industry"
    }


def test_planner_never_invents_missing_module():
    assert build_composition_plan(frame, candidates, pattern="missing") is None
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest -q tests/test_composition_planner.py`
Expected: FAIL because the planner does not exist.

- [ ] **Step 3: Implement patterns and planner**

Patterns:

- `metric_lookup`
- `metric_threshold`
- `metric_threshold_compare`
- `trend_then_drilldown`
- `report_chapter`

The planner binds entities and filters, selects compatible modules, generates
edges, adds output nodes, and returns `None` when the pattern cannot be satisfied.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest -q tests/test_composition_planner.py tests/test_composition_validator.py`

```bash
git add backend/app/services/composition_planner.py backend/app/services/composition_patterns.py backend/tests/test_composition_planner.py
git commit -m "feat: add composition planner and patterns"
```

## Task 4: Seed Composition Modules From Existing Registry

**Files:**
- Create: `backend/app/services/composition_catalog.py`
- Test: `backend/tests/test_composition_catalog.py`

- [ ] **Step 1: Write failing catalog tests**

```python
def test_catalog_exposes_at_least_sixty_modules():
    catalog = build_composition_catalog()
    assert len(catalog) >= 60


def test_catalog_contains_metric_operator_and_chapter_modules():
    kinds = {module.kind for module in build_composition_catalog().values()}
    assert {"metric", "operator", "chapter"} <= kinds
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest -q tests/test_composition_catalog.py`
Expected: FAIL because the catalog does not exist.

- [ ] **Step 3: Build the catalog**

Map validated metrics, threshold rules, existing operator contracts, chapters,
FAQ entries, and report blocks into `ModuleSpec` objects. Planned modules remain
disabled and cannot be selected.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest -q tests/test_composition_catalog.py`

```bash
git add backend/app/services/composition_catalog.py backend/tests/test_composition_catalog.py
git commit -m "feat: seed composition module catalog"
```

## Task 5: Semantic Frame And Primary Integration

**Files:**
- Create: `backend/app/schemas/semantic_frame.py`
- Modify: `backend/app/services/semantic_primary.py`
- Test: `backend/tests/test_semantic_frame_integration.py`

- [ ] **Step 1: Write failing frame integration tests**

```python
def test_route_to_semantic_frame_preserves_policy_and_metrics():
    frame = frame_from_route(route, query="企业1资产负债率和现金流怎么样")
    assert frame.policy_route == "analysis"
    assert frame.task_type == "multi_metric"


@pytest.mark.asyncio
async def test_primary_uses_validated_composition(monkeypatch):
    out = await run_primary_turn(...)
    assert out["data"]["primary"]["composition_id"]
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest -q tests/test_semantic_frame_integration.py`

- [ ] **Step 3: Implement the frame and composition handoff**

Map policy route, entities, metrics, scope, references, language, and output
requirements into `SemanticFrame`. Use the composition planner for supported
multi-step analysis. Keep the existing single-tool path as a fallback.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest -q tests/test_semantic_frame_integration.py tests/test_semantic_primary.py`

```bash
git add backend/app/schemas/semantic_frame.py backend/app/services/semantic_primary.py backend/tests/test_semantic_frame_integration.py
git commit -m "feat: integrate semantic frames with composition plans"
```

## Task 6: Async Staging Verification And Full Audit

**Files:**
- Create: `backend/scripts/run_staging_composition_matrix.py`
- Test: `backend/tests/test_staging_composition_matrix.py`
- Report: `报告/阶段11-组合内核异步验收.md`

- [ ] **Step 1: Write failing matrix tests**

```python
def test_composition_matrix_covers_atomic_and_composite_cases():
    plan = build_composition_query_plan([{"enterprise_id": "e1", "name": "企业1"}])
    assert len(plan) >= 30
    assert any(item["kind"] == "composite" for item in plan)
```

- [ ] **Step 2: Implement the real staging matrix**

Run at least 30 atomic and composite queries through HTTP staging. Verify plan
validation, output claims, no fallback, latency metrics, and persisted history.

- [ ] **Step 3: Run full verification**

```text
targeted composition tests pass
full backend regression passes
staging composition matrix passes
real report PDF still passes
retirement audit remains fail-closed
```

- [ ] **Step 4: Update plan, runbook, redline, and Stage 11 evidence report**

```bash
git add backend/scripts/run_staging_composition_matrix.py backend/tests/test_staging_composition_matrix.py 报告/阶段11-组合内核异步验收.md docs/superpowers/plans/2026-09-16-mingjian-semantic-rag-v2.md 报告/语义RAG预发布与影子评估部署手册.md 红线要求.md
git commit -m "docs: record composition kernel verification"
```

## Self-Review Checklist

- [ ] Composition plans are typed and validated before execution.
- [ ] Module combinations are generated, not enumerated.
- [ ] Independent nodes execute concurrently with bounded concurrency.
- [ ] Timeout, retry, fallback, and cancellation are explicit.
- [ ] The catalog has at least 60 retrievable modules.
- [ ] Semantic Policy remains separate from composition planning.
- [ ] Claims remain the only numeric truth source.
- [ ] Full regression and staging gates are mandatory.
