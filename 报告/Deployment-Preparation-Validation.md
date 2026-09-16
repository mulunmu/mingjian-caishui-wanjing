# Deployment Preparation Validation

Date: 2026-09-16

## Added

- `SHADOW_SEMANTIC_ENABLED` support in Docker Compose and environment templates.
- `scripts.verify_semantic_readiness --apply`.
- `scripts.shadow_evaluation_report`.
- Deployment, shadow evaluation, and rollback runbook.

## PostgreSQL Fresh-Deployment Test

The complete pre-production flow was run against a disposable PostgreSQL 16
container:

```text
python -m scripts.verify_semantic_readiness --apply
```

Result:

```json
{
  "ok": true,
  "missing_tables": [],
  "metric_status": {"validated": 52, "planned": 48},
  "tool_status": {"validated": 60, "planned": 48},
  "threshold_status": {"validated": 14, "planned": 2},
  "planned_enabled_tools": [],
  "applied_seed": {
    "metrics": 100,
    "tools": 108,
    "aliases": 305,
    "thresholds": 16
  }
}
```

## Deployment Gate

The shadow report requires at least 20 samples and:

- route match rate >= 95%
- domain match rate >= 95%
- average tool coverage >= 75%
- switch-eligible rate >= 80%

No production traffic is switched by this preparation.

## Full Regression

```text
1139 passed
13 skipped
0 failed
```