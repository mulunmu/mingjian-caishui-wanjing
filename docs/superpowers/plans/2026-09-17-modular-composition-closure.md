# Modular Composition Closure Plan

## Goal

Complete the domain module system so dialogue intents, RAG tools, deterministic
execution, long-term conversation state, and report blocks can be assembled under
scenario constraints without arbitrary composition or unexplained composition gaps.

## Stage 14A: Module Contract And Coverage Audit

- [x] Audit metrics, aliases, thresholds, tools and executors.
- [x] Identify validated metrics without executors.
- [x] Identify executable metrics without retrieval aliases or thresholds.
- [x] Validate every report chapter dependency resolves to an executable metric.
- [x] Emit machine-readable and human-readable coverage reports.

## Stage 14B: Scenario Compatibility And Adapters

- [ ] Define scenario tags and typed ports for modules.
- [ ] Define compatibility rules and adapter modules for common conversions.
- [ ] Prove in-domain composition closure with pair/triple matrices.
- [ ] Return controlled clarify/abstain only for genuine data or domain gaps.

## Stage 14C: Long-Term Conversation Memory

- [ ] Add layered memory: recent turns, topic summaries, session summary,
      entity/filter index and artifact references.
- [ ] Support references across 10+ intervening turns.
- [ ] Persist durable state in PostgreSQL; keep Redis as hot cache only.
- [ ] Add compression and retrieval regression tests.

## Stage 14D: LangGraph Outer Orchestration

- [ ] Add LangGraph in an isolated dependency group.
- [ ] Build adapters around existing DialogAct, Tool RAG, ToolPlan, reports and memory.
- [ ] Keep AsyncDagRuntime as the deterministic inner execution layer.
- [ ] Add feature flag and dual-engine parity tests.
- [ ] Add interrupt/resume for report confirmation and approvals.

## Stage 14E: Dialogue Intent And Content Assembly

- [ ] Represent intent, policy and content as typed modules.
- [ ] Compose modules only through validated graphs.
- [ ] Support multi-intent requests and cross-topic follow-ups.
- [ ] Preserve Claim-only numeric truth boundaries.

## Stage 14F: Report Block Composition

- [ ] Define chapter, metric block, comparison block, trend block and synthesis block.
- [ ] Validate all 30+ combinations for chapter and block compatibility.
- [ ] Persist block-level report snapshots and render them consistently.
- [ ] Verify PDF, API detail and frontend use the same block tree.

## Stage 14G: End-To-End Verification

- [ ] Run 105+ dialogue cases.
- [ ] Run 30+ report combinations.
- [ ] Run 10+ turn memory and topic-rollback cases.
- [ ] Compare custom DAG and LangGraph on correctness, latency and recovery.
- [ ] Run full regression and production smoke tests.

## Stage 14H: Freeze And Operations

- [ ] Freeze dependency versions and rollback switches.
- [ ] Update redline, runbooks, architecture documentation and rollout report.
- [ ] Tag the accepted candidate.
