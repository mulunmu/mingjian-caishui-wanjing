# Metric Catalog V2 Audit

Date: 2026-09-16

## Current Coverage

| Item | Count |
|---|---:|
| `core_metrics` columns | 55 |
| Canonical retrieval metrics | 22 |
| Source fields | 36 |
| P0 metric candidates | 66 |

All 36 declared source fields are present in `core_metrics`. The primary gap is
that many core fields are not registered as retrieval tools, and many important
metrics require aggregation over source tables not represented in `core_metrics`.

## Metric Layers

1. Atomic metrics: one field or one direct aggregation.
2. Time-series metrics: monthly/quarterly/annual values, trends, volatility.
3. Counterparty metrics: customer/supplier counts, concentration, HHI.
4. Composite scenario tools: stability, shell risk, invoice anomaly, tax
   compliance, loan readiness, growth quality.
5. Report chapter tools: deterministic chapter composition.

## P0 Categories

| Category | Examples |
|---|---|
| Profile | enterprise age, capital, employees, taxpayer type, operation status, changes |
| Invoice | amount, count, continuity, red invoice ratio, void rate, check exceptions |
| Counterparty | customer/supplier count, TOP1/TOP5 concentration, HHI, new counterparty ratio |
| Tax | declared revenue, input/output tax, burden, zero declarations, arrears, late days |
| Legal | violation recency and event history |
| Social | headcount, trend, contribution ratio |
| Financial | current/quick ratio, debt ratio, margins, ROE, ROA, OCF/revenue |
| Scenario | operating deterioration, stability, shell risk, invoice anomaly, tax compliance, loan readiness, growth quality |

## Implementation Rule

- All atomic definitions should be inventoried before retrieval integration.
- Threshold rules are versioned and can change without changing metric identity.
- Composite and chapter tools may be delivered in tranches.
- Only tools with status `validated` participate in retrieval.
- `planned` and `draft` tools must never be visible to the planner.

## Executable Audit

Run:

```text
python -m scripts.audit_metric_catalog
```

The command prints the current counts, missing canonical registrations, source
field coverage, and the 66 P0 candidate definitions.

## Stage 3 Seed Result

The idempotent Registry seed now writes:

```text
metrics=84
tools=92
aliases=184
thresholds=16
```

Implemented metrics are marked `validated` and enabled. Definitions that do not
yet have a backend computation remain `planned` with `enabled=false`, so they
cannot be selected by future Tool RAG until their implementation and formula
tests are complete.
