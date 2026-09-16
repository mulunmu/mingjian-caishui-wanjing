# Tool RAG V1 Validation

Date: 2026-09-16

## Implemented

- Database-backed tool snapshot loading.
- Only `status=validated` and `enabled=true` tools are loaded.
- Exact ID, title, alias, example, description, and document-overlap scoring.
- Domain scenario boost.
- Question-filler normalization.
- Multilingual aliases.
- Deterministic route normalization.

## Retrieval Contract

Each candidate exposes:

- tool identity and kind
- title and description
- score and matched fields
- dependencies
- chapter links
- scenarios
- output shape
- retrieval document text

The retrieval document is suitable for a future BM25 or vector index without
changing the tool plan contract.

## Validation

Human-authored queries:

```text
cases=64
Recall@5=100%
misses=0
```

Registry state:

```text
metrics=100
tools=108
aliases=303
thresholds=16
```

Planned tools are excluded:

- `scenario_loan_readiness`
- `scenario_business_stability`
- `scenario_shell_company_risk`
- `scenario_invoice_anomaly`

## Test Evidence

```text
13 stage-specific tests passed
Full backend suite: 1104 passed, 9 skipped, 0 failed
```
