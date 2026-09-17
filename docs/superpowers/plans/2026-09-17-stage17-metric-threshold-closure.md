# Stage 17 Metric And Threshold Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all 48 planned metrics and 2 planned thresholds by either implementing a deterministic executor with real source data, or marking the metric unsupported with an explicit missing-data reason.

**Architecture:** Add a Stage 17 extended-metric catalog and executor layer over `enterprise_invoice_profile`, `enterprise_tax_profile`, `enterprise_financials`, `enterprise_engine_features`, `legal_events`, and `core_metrics`. Seed supported metrics as validated and unsupported metrics as disabled, then make strict audit require `planned_metrics=0`.

**Tech Stack:** Python 3.12, SQLAlchemy AsyncSession, Pydantic, PostgreSQL, existing semantic registry and RAG snapshot. No LLM may generate or alter metric values.

---

### Task 1: Data Availability Catalog

**Files:**
- Create: `backend/app/services/stage17_metric_catalog.py`
- Test: `backend/tests/test_stage17_metric_catalog.py`

- [x] Define `SUPPORTED_EXTENDED_METRICS` with 15 planned metrics backed by real columns: `change_count`, `customer_count`, `customer_hhi`, `customer_top5_concentration`, `income_tax_effective_rate`, `invalid_invoice_ratio`, `invoice_amount_total`, `ocf_to_revenue`, `red_invoice_count_ratio`, `supplier_count`, `supplier_hhi`, `supplier_top5_concentration`, `vat_declared_revenue`, `violation_recency_days`, `void_invoice_ratio`.
- [x] Define `CROSS_DEVIATION_METRICS` for `cross_avg_deviation` and `cross_max_deviation` using `authenticity_engine.cross_source_deviation`.
- [x] Define `UNSUPPORTED_METRICS` with the remaining planned keys and a concrete reason for each missing field or time series.
- [x] Add tests that supported and unsupported keys are disjoint, every P0 planned key appears exactly once, and every unsupported reason is non-empty.
- [x] Run `python -m pytest tests/test_stage17_metric_catalog.py -q`; expect all tests to pass.
- [x] Commit the catalog.

### Task 2: Deterministic Extended Metric Executors

**Files:**
- Create: `backend/app/services/extended_metric_executors.py`
- Test: `backend/tests/test_extended_metric_executors.py`
- Modify: `backend/app/services/judgment_service.py`

- [x] Implement pure ratio helpers that return `None` for zero denominators instead of fake zero values.
- [x] Implement profile metric calculations for customer/supplier concentration, invoice amount, invalid/red/void ratios, and VAT declared revenue.
- [x] Implement financial ratios for `ocf_to_revenue` and `income_tax_effective_rate` using a positive-profit denominator only.
- [x] Implement legal recency from `legal_events.event_date`; return no coverage when an enterprise has no dated event.
- [x] Implement cross-source deviation metrics from `vat_revenue`, `invoice_revenue`, and `finance_revenue` with the existing `cross_source_deviation` function.
- [x] Add tests for every pure calculator, including zero-denominator abstention and JSON TOP5 fallback.
- [x] Route extended metrics in `judgment_service._metric_dispatcher` before generic core-metric averaging.
- [x] Run focused executor tests; expect all tests to pass.
- [x] Commit the executor layer.

### Task 3: Registry And Unsupported Lifecycle

**Files:**
- Modify: `backend/app/services/semantic_registry_seed.py`
- Modify: `backend/app/scripts/audit_module_coverage.py`
- Modify: `backend/tests/test_module_coverage_audit.py`

- [x] Seed supported Stage 17 metrics as `validated`, enabled, retrieval-enabled with aliases and source tables.
- [x] Seed unsupported metrics as `unsupported`, disabled, retrieval-disabled, retaining aliases only for explanation and future promotion.
- [x] Add audit fields `metrics_unsupported`, `unsupported_metric_keys`, and `unsupported_metric_reasons`.
- [x] Make strict audit fail when `metrics_planned != 0` or any unsupported metric is retrieval-enabled/tool-enabled.
- [x] Add tests for lifecycle idempotency: rerunning seed must not turn `unsupported` back into `planned`.
- [x] Run registry and audit tests; expect all tests to pass.
- [x] Commit registry lifecycle changes.

### Task 4: Threshold Closure

**Files:**
- Modify: `backend/app/services/semantic_registry_seed.py`
- Modify: `backend/app/services/metric_registry.py`
- Test: `backend/tests/test_stage17_thresholds.py`

- [x] Add `cross_avg_deviation` and `cross_max_deviation` metric definitions with formula, source fields, unit, aliases, and executor registration.
- [x] Validate both threshold rules only after their source metric tools are validated and executor tests pass.
- [x] Add boundary tests for exactly-0.25, below-0.25, above-0.25, exactly-0.40, below-0.40, and above-0.40.
- [x] Run threshold tests and the strict audit; expect `planned_thresholds=0`.
- [x] Commit threshold closure.

### Task 5: RAG, Reports And Runbook

**Files:**
- Modify: `backend/app/services/tool_rag.py` if snapshot filtering needs unsupported exclusion.
- Modify: `docs/runbooks/rag-v2-stage14-rollout-rollback.md`
- Create: `报告/阶段17-指标与阈值闭环报告.md`

- [x] Verify supported metrics enter the validated RAG snapshot and unsupported metrics remain invisible.
- [x] Add a runbook section describing supported sources, unsupported metrics, promotion rules, and audit commands.
- [x] Record real-data coverage counts and executor examples in the Stage 17 report.
- [x] Run readiness, strict coverage audit, and the report block matrix.
- [x] Commit documentation and evidence.

### Task 6: Full Closure

**Files:**
- Modify: `docs/superpowers/plans/2026-09-17-stage17-metric-threshold-closure.md`

- [x] Run the full backend regression.
- [x] Run the production 105-case dialogue matrix twice.
- [x] Run `python -m scripts.audit_module_coverage --strict` in the production container.
- [x] Confirm `registry_metrics_total`, `metrics_validated`, `metrics_unsupported`, and `metrics_planned=0` from fresh output.
- [x] Tag the accepted Stage 17 candidate only after all evidence above passes.
