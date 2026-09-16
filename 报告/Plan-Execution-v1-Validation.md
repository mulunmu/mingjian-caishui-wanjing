# Plan Validation and Execution V1

Date: 2026-09-16

## Typed Plan

Each plan contains:

- mode: answer, clarify, or report
- steps
- step IDs
- tool IDs
- parameters
- explicit step dependencies

## Validation

The validator rejects:

- duplicate step IDs
- unknown tool IDs
- missing required parameters
- missing explicit dependencies
- missing required registry tools
- dependency cycles
- execution when conversation policy denies it

Validation runs before any tool function is called.

## Execution

Execution follows topological order:

```text
validate
-> topologically sort
-> resolve dependency outputs
-> call deterministic tool function
-> canonicalize output
-> aggregate claims
```

## Evidence

```text
7 stage-specific tests passed
5 PostgreSQL integration tests passed
Full backend suite: 1122 passed, 10 skipped, 0 failed
```

Verified:

- invalid plans never call the executor
- repeated plan execution produces identical claims
- PostgreSQL Registry snapshots execute plans correctly
