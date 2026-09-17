# Stage 16: Production Quality, Observability And Closure

## Goal

Remove the production-quality blockers found by the Stage 16 preflight audit:
missing traceability, internal metric field leakage, repeated surface text,
high latency, unbounded checkpoint state and undeployed approval lifecycle
guards.

## Stage 16A: Trace And Sentry

- [x] Add request-scoped trace IDs and response headers.
- [x] Propagate trace IDs through LangGraph agent traces and chat metadata.
- [x] Add safe optional Sentry initialization.
- [x] Add trace and Sentry regression tests.

## Stage 16B: Surface Quality

- [x] Map every validated metric to a Chinese surface label.
- [x] Replace internal metric keys in replies and reports.
- [x] Collapse accidental repeated Chinese phrases.
- [x] Add leakage and repeated-text regression tests.

## Stage 16C: Runtime Metrics

- [x] Track request, route, agent, RAG, claim, report and error counters.
- [x] Track latency summaries with bounded cardinality.
- [x] Expose an admin observability endpoint.
- [x] Add Redis-backed metrics with process-local fallback.

## Stage 16D: Latency And Lifecycle

- [x] Measure request stages before changing model behavior.
- [x] Keep LLM generation as the core path and enforce bounded latency plus model escalation.
- [x] Add approval expiry and safe stale-interrupt handling.
- [x] Add checkpoint retention cleanup with a safe command.

## Stage 16E: Rollback Drill

- [x] Start the pre-LangGraph image against staging data.
- [x] Verify health, greeting and analysis behavior.
- [x] Remove the drill container and record evidence.

## Stage 16F: Full Closure

- [x] Run 105+ production dialogue cases.
- [x] Run strict coverage and readiness audits.
- [x] Run full backend regression and frontend build.
- [x] Tag the accepted Stage 16 candidate.

## Stage 16G: LLM Correctness-Preserving Latency

- [x] Keep every user-visible analytical answer LLM-generated.
- [x] Remove fixed-template and raw-Claim fallback from the core reply path.
- [x] Classify with one non-blocking schema-constrained instructor call and no hidden retries.
- [x] Use one fast async JSON authoring call on the common path.
- [x] Escalate to one schema-constrained pro path only when the fast authoring call fails.
- [x] Allow one explicit schema-repair retry on the pro path when conclusions are empty or malformed.
- [x] Parse fenced or wrapped JSON without spending a second model call.
- [x] Close the response with a controlled 503 when no valid LLM answer exists.
- [x] Re-run the 105-case production dialogue matrix twice with 105/105 success.
