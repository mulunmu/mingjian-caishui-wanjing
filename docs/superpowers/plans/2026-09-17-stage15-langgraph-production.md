# Stage 15: LangGraph Production And Semantic Topic Recall

## Goal

Make LangGraph the default outer orchestration layer in production without moving
financial truth out of deterministic Claims and executors. Improve long
conversation recall so users can refer to prior content instead of exact turn
numbers. Represent the outer graph as explicit collaborating agents.

## Stage 15A: Semantic Topic Recall

- [x] Detect explicit and content-based references to previous topics.
- [x] Resolve references by keyword and semantic overlap, with a confidence floor.
- [x] Return matched topic metadata for auditability.
- [x] Add 10+ turn content-reference tests.

## Stage 15B: LangGraph Agent Roles

- [x] Add explicit memory, classification, planning, approval, execution and verification agents.
- [x] Persist role-level trace metadata in the response.
- [x] Keep the deterministic primary pipeline and AsyncDagRuntime inside execution.
- [x] Add graph parity, interrupt/resume and recovery tests.

## Stage 15C: Production Enablement

- [x] Build the production backend with `INSTALL_ORCHESTRATION=true`.
- [x] Enable `LANGGRAPH_OUTER_ENABLED=true` and PostgreSQL checkpointing.
- [x] Preserve a tagged pre-LangGraph rollback image.
- [x] Run health, dialect, approval and report smoke tests.

## Stage 15D: Final Audit

- [x] Run full regression with LangGraph installed.
- [x] Run strict coverage/readiness gates.
- [x] Tag the accepted canary candidate.
