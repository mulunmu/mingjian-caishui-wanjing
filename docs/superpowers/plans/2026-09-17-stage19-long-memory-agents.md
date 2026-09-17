# Stage 19 Long Memory And Agent Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make long conversations recover prior topics by content, compress topic history safely, correct mistaken references, and add explicit finance-review, final-guard and agent-budget controls without allowing optional agents to own facts.

**Architecture:** Keep `ConversationTopic` as durable truth. Add optional semantic topic matching over topic summaries, deterministic layered compression and correction detection. Extend the LangGraph outer graph with finance-review and final-guard nodes, bounded by an explicit per-turn time budget and fail-open/fail-closed rules that never bypass factual execution or the final hallucination guard.

**Tech Stack:** FastEmbed BGE-small-zh, PostgreSQL topic memory, LangGraph state nodes, existing Claims and hallucination guard.

---

### Task 1: Long-Memory Compression And Semantic Recall

**Files:**
- Modify: `backend/app/services/topic_memory.py`
- Create: `backend/tests/test_stage19_long_memory.py`

- [x] Add deterministic de-duplicating compression for topic summaries with recency priority.
- [x] Add optional semantic cosine matching over topic summaries through the cached embedding provider.
- [x] Combine semantic and bigram match scores without changing ordinal-reference behavior.
- [x] Add correction markers and expose `correction_detected`, `referenced_topic_id`, and match reason in memory context.
- [x] Test 40-turn histories, unrelated intervening turns, N-2 rollback and content-based back-reference.
- [x] Commit long-memory changes.

### Task 2: Finance Review Agent

**Files:**
- Modify: `backend/app/services/outer_orchestrator.py`
- Modify: `backend/app/services/llm_reply.py`
- Test: `backend/tests/test_outer_orchestrator.py`

- [x] Add `LANGGRAPH_FINANCE_REVIEW_ENABLED` and a `finance_review_agent` graph node.
- [x] When configured, review Claims and produce causal interpretation without adding or changing numbers.
- [x] When the financial model is absent, record `skipped` and continue the normal semantic path.
- [x] Store finance-review output only in metadata; final answer still comes from the LLM authoring layer plus deterministic Claims.
- [x] Test configured, skipped and failure paths.
- [x] Commit finance review.

### Task 3: Final Guard And Agent Budget

**Files:**
- Modify: `backend/app/services/outer_orchestrator.py`
- Test: `backend/tests/test_outer_orchestrator.py`

- [x] Add `LANGGRAPH_FINAL_GUARD_ENABLED` and a deterministic `final_guard_agent` node.
- [x] Reject empty replies, fallback responses and untraceable non-empty Claims.
- [x] Add `LANGGRAPH_AGENT_BUDGET_MS` to bound total agent orchestration time.
- [x] Record per-agent elapsed time, budget use and stop/fail reason in the trace.
- [x] Test success, guard rejection and budget exhaustion.
- [x] Commit final guard and budget.

### Task 4: Long-Conversation Production Evidence

**Files:**
- Create: `backend/scripts/run_stage19_long_dialogue.py`
- Modify: `docs/runbooks/rag-v2-stage14-rollout-rollback.md`
- Create: `报告/阶段19-长对话与Agent闭环报告.md`

- [x] Run at least four 40-turn conversations with unrelated topic interruptions.
- [x] Include content-based back-reference, N-2 rollback, correction and ambiguity cases.
- [x] Verify topic write and retrieval survive restart and do not depend on Redis.
- [x] Run readiness, strict audit, full regression and two 105-case matrices.
- [x] Record exact pass rates, latency and skipped optional agents.
- [x] Commit evidence.

### Task 5: Closure

- [x] Confirm no new `planned` or `unsupported` leakage.
- [x] Confirm optional finance review absence never blocks core dialogue.
- [x] Confirm final guard cannot be bypassed.
- [x] Tag `rag-v2-stage19-accepted-20260917` only after all evidence passes.
