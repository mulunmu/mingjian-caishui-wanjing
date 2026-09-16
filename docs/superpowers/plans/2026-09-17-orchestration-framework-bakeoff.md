# Orchestration Framework Bake-off

## Decision

Keep `AsyncDagRuntime` as the production orchestration path for deterministic
financial execution and report assembly. Evaluate LangGraph only in isolated
workflows that need native interrupts, cyclic agents, long-running state, or
streaming events.

## Evidence

- `backend/experiments/langgraph_orchestration_bakeoff.py`
- `报告/阶段13-编排框架对照验证.md`

## Acceptance

```text
same DAG result
same retry outcome
checkpoint restore
interrupt/resume capability
dependency isolation
```

## Non-Goals

- Do not add LangGraph to production requirements in this stage.
- Do not replace the existing Claim, tool, or report truth boundaries.
