# Stage 20 Financial Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the financial semantic/review layer asynchronous, configurable and measurable, then evaluate an API baseline and decide whether local deployment is feasible on the actual hardware.

**Architecture:** Keep Claims as the only facts. A financial model adapter accepts only existing Claim text, produces causal interpretation without digits, and returns metadata to the finance-review Agent. API and OpenAI-compatible local endpoints share one provider interface.

**Tech Stack:** LiteLLM/OpenAI-compatible APIs, Instructor JSON mode, existing finance-review LangGraph node.

---

### Task 1: Financial Model Configuration And Async Adapter

**Files:**
- Create: `backend/app/services/financial_model.py`
- Modify: `backend/app/services/llm_reply.py`
- Test: `backend/tests/test_financial_model.py`

- [x] Resolve `FINANCIAL_LLM_*` with fallback to the main LLM only for API-baseline evaluation.
- [x] Expose provider, model, availability, base URL presence and local/API mode without exposing the key.
- [x] Replace synchronous Instructor/LiteLLM calls in `generate_financial_interpretation` with the async Instructor JSON path.
- [x] Reject any generated sentence containing digits and keep the existing no-new-fact rule.
- [x] Test configured, missing-key, numeric-output rejection and provider-error paths.
- [x] Commit the adapter.

### Task 2: Financial Evaluation Harness

**Files:**
- Create: `backend/app/services/financial_model_eval.py`
- Create: `backend/scripts/evaluate_financial_model.py`
- Test: `backend/tests/test_financial_model_eval.py`

- [x] Define at least 10 cases covering leverage, cash flow, tax burden, invoice anomalies and profitability.
- [x] Score output for non-empty response, zero digits, causal connector, required concept coverage and latency.
- [x] Return `skipped` when no model is configured; never mark skipped as passed.
- [x] Test the deterministic scorer without calling a model.
- [x] Commit evaluation harness.

### Task 3: API Baseline Evaluation

**Files:**
- Modify: `docker-compose.yml`, `.env.example`, `backend/.env.example`
- Create: `报告/阶段20-金融模型API基线评测.json`

- [x] Configure DeepSeek Pro as the API baseline through the financial adapter, without claiming it is a specialized finance model.
- [x] Enable `LANGGRAPH_FINANCE_REVIEW_ENABLED=true` for the baseline run.
- [x] Run all evaluation cases and record pass rate, digit leakage, latency and failures.
- [x] Keep the baseline out of factual ownership and outside the deterministic Claim path.
- [x] Commit configuration and evidence.

### Task 4: Local Deployment Decision

**Files:**
- Create: `报告/阶段20-本地金融模型部署评估.md`

- [x] Record actual hardware: GPU model/memory, system RAM and disk availability.
- [x] Compare candidates: DISC-FinLLM 13B, XuanYuan-6B-4bit and FinGPT/Llama candidates.
- [x] Verify license, model size and expected serving memory from upstream repositories.
- [x] Mark local deployment feasible/not feasible for the current machine and specify the required production hardware.
- [x] Do not download or deploy a model unless hardware and license gates pass.

### Task 5: Closure

- [x] Run readiness, strict audit, financial-model evaluation and full regression.
- [x] Run two 105-case dialogue matrices with finance-review enabled.
- [x] Verify optional finance review never changes numbers or final facts.
- [x] Tag `rag-v2-stage20-accepted-20260917` only after all evidence passes.
