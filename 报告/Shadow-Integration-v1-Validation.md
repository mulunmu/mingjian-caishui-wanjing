# Shadow Integration V1 Validation

Date: 2026-09-16

## Design

The legacy chat path remains authoritative. When `SHADOW_SEMANTIC_ENABLED=true`,
the chat API records a post-response comparison after the legacy response has
already succeeded.

The hook is intentionally:

- default-off
- post-response only
- privacy-minimized using a SHA-256 query digest
- non-blocking through `run_blocking`
- exception-isolated so shadow failures cannot affect user responses

## Compared Fields

- legacy route versus shadow route
- domain mapping
- legacy function and query type
- candidate tool IDs
- expected tool IDs for the legacy function
- tool coverage
- legacy and shadow latency
- mismatch reasons
- switch eligibility

## Safety Gate

A shadow result is eligible for a future traffic switch only when:

- route matches
- domain is compatible
- tool coverage is at least 50%
- analysis/report results contain candidates
- shadow latency is not more than three times legacy latency and not over 2 seconds

No traffic is switched in this stage.

## Evidence

```text
8 shadow hook/integration tests passed
7 PostgreSQL integration tests passed
Full backend suite: 1149 passed, 13 skipped, 0 failed
```

Verified that shadow failures are swallowed and the legacy response remains
unchanged.