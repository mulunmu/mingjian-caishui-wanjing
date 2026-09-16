# Semantic Primary Implementation Plan

> Execution status 2026-09-17: Stage 10 is closed. Semantic primary, all route
> policies, session and topic persistence, canary-free primary selection, the 32-case
> staging matrix, and six-turn N-2 memory validation are implemented and verified.
> Production rollout and legacy retirement remain governed by Stage 9.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make semantic dialogue the primary path for all 12 supported route kinds while retaining legacy only for internal failures.

**Architecture:** Add a deterministic primary selector, deterministic non-analysis handlers, one semantic primary orchestrator, and a single persistence writer for session history and topic threads. The chat endpoint returns the primary response before legacy is invoked; legacy runs only on internal failure.

**Tech Stack:** FastAPI, Pydantic, Async SQLAlchemy, synchronous topic-memory sessions, pytest, Docker Compose, PostgreSQL staging.

---

## File Structure

- Create `backend/app/services/rollout.py`: stable percentage parsing and bucket selection shared by canary and primary.
- Create `backend/app/services/non_analysis_replies.py`: deterministic responses for all non-tool routes.
- Create `backend/app/services/semantic_primary.py`: primary orchestration, result adaptation, fallback decisions.
- Modify `backend/app/services/topic_memory.py`: add a durable append helper used by primary.
- Modify `backend/app/services/session_store.py`: report persistence success from `store_session`.
- Modify `backend/app/services/semantic_answer_composer.py`: remove `not_applicable` from the primary contract by supporting formal outcomes.
- Modify `backend/app/api/v1/chat.py`: primary selection before legacy, canonical response conversion, fallback handling.
- Modify configuration files: `.env.example`, `backend/.env.example`, `docker-compose.yml`.
- Create `backend/scripts/run_staging_primary_matrix.py` and tests for its query plan and validation.
- Modify operational docs and add the Stage 10 evidence report.

## Task 1: Stable Primary Selection

**Files:**
- Create: `backend/app/services/rollout.py`
- Modify: `backend/app/services/canary_router.py`
- Test: `backend/tests/test_rollout.py`

- [x] **Step 1: Write failing rollout tests**

```python
from app.services.rollout import is_selected, normalize_percent, stable_bucket


def test_stable_bucket_is_deterministic():
    assert stable_bucket("s1") == stable_bucket("s1")
    assert 0 <= stable_bucket("s1") < 100


def test_percent_is_fail_safe():
    assert normalize_percent("invalid") == 0.0
    assert normalize_percent("nan") == 0.0
    assert normalize_percent(-1) == 0.0
    assert normalize_percent(101) == 100.0
    assert is_selected("s1", 0) is False
    assert is_selected("s1", 100) is True
```

- [x] **Step 2: Run and verify RED**

Run: `python -m pytest -q tests/test_rollout.py`
Expected: FAIL because `app.services.rollout` does not exist.

- [x] **Step 3: Implement rollout.py**

```python
import hashlib
import math


def stable_bucket(key: str) -> int:
    digest = hashlib.sha256((key or "").encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def normalize_percent(value) -> float:
    try:
        percent = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(percent):
        return 0.0
    return max(0.0, min(percent, 100.0))


def is_selected(key: str, percent) -> bool:
    value = normalize_percent(percent)
    if value <= 0:
        return False
    if value >= 100:
        return True
    return stable_bucket(key) < value
```

- [x] **Step 4: Refactor canary to use the shared utility**

In `canary_router.py`, import `is_selected`, `normalize_percent`, and call the shared functions from `canary_bucket`, `is_canary_selected`, and `canary_percent`.

- [x] **Step 5: Verify GREEN and commit**

Run: `python -m pytest -q tests/test_rollout.py tests/test_canary_routing.py`
Expected: PASS.

```bash
git add backend/app/services/rollout.py backend/app/services/canary_router.py backend/tests/test_rollout.py
git commit -m "feat: add stable semantic rollout selection"
```

## Task 2: Deterministic Non-Analysis Handlers

**Files:**
- Create: `backend/app/services/non_analysis_replies.py`
- Test: `backend/tests/test_non_analysis_replies.py`

- [x] **Step 1: Write the failing route matrix test**

```python
from app.schemas.conversation_route import ConversationPolicyRegistry, ConversationRoute
from app.services.non_analysis_replies import build_non_analysis_turn


def test_all_non_analysis_routes_have_formal_reply():
    routes = [
        "greeting", "capability", "product_faq", "feedback", "out_of_domain",
        "abuse", "language_switch", "unknown_entity", "clarify", "refuse",
    ]
    for route_name in routes:
        route = ConversationRoute(route=route_name, domain="general")
        out = build_non_analysis_turn(route, "你好", policy=ConversationPolicyRegistry.resolve(route))
        assert out.status in {"answered", "clarify", "abstain"}
        assert out.reply
        assert out.route.route == route_name
```

- [x] **Step 2: Run and verify RED**

Run: `python -m pytest -q tests/test_non_analysis_replies.py`
Expected: FAIL because the module does not exist.

- [x] **Step 3: Implement deterministic handlers**

```python
def build_non_analysis_turn(route, query, *, policy):
    from app.services.faq_kb import build_faq_claims

    replies = {
        "greeting": ("你好。我是明鉴财税风控助手，可以继续分析企业风险，也可以直接问功能、口径或报告。", "answered"),
        "capability": ("我可以分析企业财务、税务、发票、真实性、风险信号、评级与报告；也可以解释系统功能和指标口径。", "answered"),
        "feedback": ("已收到你的反馈。系统会保留这条意见，但不会自动承诺功能变更。", "answered"),
        "out_of_domain": ("这个问题超出了当前财税风控数据范围。我可以继续帮你看企业经营、税务、发票和风险预警。", "abstain"),
        "abuse": ("我会继续按事实边界协助你。你可以直接说想查的企业、指标或报告类型。", "answered"),
        "language_switch": ("I can continue in English or switch back to Chinese. Which enterprise or financial metric should I analyze?", "answered"),
        "unknown_entity": ("没有找到对应企业，请提供企业名称或脱敏编号。", "clarify"),
        "clarify": ("请补充企业主体、指标名称或分析范围。", "clarify"),
        "refuse": ("数字、企业名单和风险结论只能来自系统真实数据，不能编造或伪造。", "abstain"),
    }
    if route.route == "product_faq":
        claims, meta = build_faq_claims(query)
        return SemanticTurnResult(
            status="answered",
            route=route,
            policy=policy,
            claims=claims,
            reply=claims[0].claim,
            reply_source="template",
            meta=meta,
        )
    reply, status = replies[route.route]
    return SemanticTurnResult(status=status, route=route, policy=policy, reply=reply, reply_source="template")
```

- [x] **Step 4: Run and verify GREEN**

Run: `python -m pytest -q tests/test_non_analysis_replies.py`
Expected: PASS for all 10 non-analysis routes.

- [x] **Step 5: Commit**

```bash
git add backend/app/services/non_analysis_replies.py backend/tests/test_non_analysis_replies.py
git commit -m "feat: add deterministic non-analysis replies"
```

## Task 3: Semantic Primary Orchestrator

**Files:**
- Create: `backend/app/services/semantic_primary.py`
- Modify: `backend/app/services/semantic_answer_composer.py`
- Test: `backend/tests/test_semantic_primary.py`

- [x] **Step 1: Write failing orchestration tests**

```python
@pytest.mark.asyncio
async def test_primary_routes_non_analysis_without_composer(monkeypatch):
    from app.services import semantic_primary

    called = False

    async def composer(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(semantic_primary, "compose_semantic_turn", composer)
    out = await semantic_primary.compose_primary_turn(
        db=object(),
        session_id="s1",
        query="你好",
        raw_route={"route": "greeting"},
    )
    assert out.status == "answered"
    assert out.route.route == "greeting"
    assert called is False


@pytest.mark.asyncio
async def test_not_applicable_is_contract_error(monkeypatch):
    from app.services import semantic_primary

    async def composer(**kwargs):
        return SemanticTurnResult(status="not_applicable", route=ConversationRoute(route="analysis"), policy=ConversationPolicyRegistry.resolve(ConversationRoute(route="analysis")))

    monkeypatch.setattr(semantic_primary, "compose_semantic_turn", composer)
    with pytest.raises(semantic_primary.PrimaryContractError):
        await semantic_primary.compose_primary_turn(
            db=object(), session_id="s1", query="分析风险", raw_route={"route": "analysis"}
        )
```

- [x] **Step 2: Run and verify RED**

Run: `python -m pytest -q tests/test_semantic_primary.py`
Expected: FAIL because the orchestrator does not exist.

- [x] **Step 3: Implement compose_primary_turn**

```python
class PrimaryContractError(RuntimeError):
    pass


async def compose_primary_turn(*, db, session_id, query, raw_route):
    route = normalize_route(raw_route, query)
    policy = ConversationPolicyRegistry.resolve(route)
    if policy.execute_tools or route.route in {"analysis", "report"}:
        result = await compose_semantic_turn(
            db=db, session_id=session_id, query=query, raw_route=raw_route
        )
    else:
        result = build_non_analysis_turn(route, query, policy=policy)
    if result.status == "not_applicable":
        raise PrimaryContractError(f"no primary policy for route={route.route}")
    return result
```

- [x] **Step 4: Ensure analysis outcomes are formal**

Adjust `semantic_answer_composer.py` so analysis/report routes never return `not_applicable`; use `clarify` for missing scope and `abstain` for no executable tools.

- [x] **Step 5: Verify GREEN and commit**

Run: `python -m pytest -q tests/test_semantic_primary.py tests/test_semantic_answer_composer.py`
Expected: PASS.

```bash
git add backend/app/services/semantic_primary.py backend/app/services/semantic_answer_composer.py backend/tests/test_semantic_primary.py
git commit -m "feat: add semantic primary orchestration"
```

## Task 4: Primary Turn Persistence

**Files:**
- Modify: `backend/app/services/session_store.py`
- Modify: `backend/app/services/topic_memory.py`
- Create: `backend/app/services/semantic_turn_persistence.py`
- Test: `backend/tests/test_semantic_turn_persistence.py`

- [x] **Step 1: Write failing persistence tests**

```python
@pytest.mark.asyncio
async def test_primary_turn_persists_history_and_topic(monkeypatch):
    from app.services import semantic_turn_persistence as stp
    from app.schemas.semantic_turn import SemanticTurnResult
    from app.schemas.conversation_route import ConversationRoute, ConversationPolicyRegistry

    calls = []
    monkeypatch.setattr(stp.session_store, "store_session", lambda *a, **k: calls.append(("history", k)) or True)
    monkeypatch.setattr(stp, "append_topic_blocking", lambda *a, **k: calls.append(("topic", k)))
    route = ConversationRoute(route="greeting")
    turn = SemanticTurnResult(
        status="answered", route=route, policy=ConversationPolicyRegistry.resolve(route), reply="你好"
    )
    await stp.persist_primary_turn(
        db=object(), session_id="s1", owner="u@example.com", query="你好", turn=turn
    )
    assert [item[0] for item in calls] == ["history", "topic"]


@pytest.mark.asyncio
async def test_history_failure_prevents_topic_write(monkeypatch):
    from app.services import semantic_turn_persistence as stp
    monkeypatch.setattr(stp.session_store, "store_session", lambda *a, **k: False)
    with pytest.raises(stp.PrimaryPersistenceError):
        await stp.persist_primary_turn(db=object(), session_id="s1", owner=None, query="你好", turn=object())
```

- [x] **Step 2: Run and verify RED**

Run: `python -m pytest -q tests/test_semantic_turn_persistence.py`
Expected: FAIL because persistence service does not exist.

- [x] **Step 3: Make store_session report success**

Change `_persist` to return `True` after commit and `False` on exception. Change `store_session` to return the boolean from `_persist`.

- [x] **Step 4: Add synchronous topic append helper**

In `topic_memory.py`, add:

```python
def append_topic_blocking(engine, *, session_id, summary, entities=None, filters=None, scenario=None, intent=None, tool_plan=None, claim_ids=None):
    with Session(engine) as session:
        append_topic(session, session_id=session_id, summary=summary, entities=entities or [], filters=filters or {}, scenario=scenario, intent=intent, tool_plan=tool_plan or [], claim_ids=claim_ids or [])
        session.commit()
```

- [x] **Step 5: Implement one primary writer**

`persist_primary_turn` must call `session_store.store_session` through `run_blocking`, verify its boolean result, then append a topic through `run_blocking`. It must derive function, dimension, summary, entities, filters, tool plan, and claim IDs from `SemanticTurnResult`.

- [x] **Step 6: Verify GREEN and commit**

Run: `python -m pytest -q tests/test_semantic_turn_persistence.py tests/test_session_store.py tests/test_topic_memory.py`
Expected: PASS.

```bash
git add backend/app/services/session_store.py backend/app/services/topic_memory.py backend/app/services/semantic_turn_persistence.py backend/tests/test_semantic_turn_persistence.py
git commit -m "feat: persist every semantic primary turn"
```

## Task 5: Chat API Primary Integration

**Files:**
- Modify: `backend/app/api/v1/chat.py`
- Modify: `backend/app/services/semantic_primary.py`
- Modify: `docker-compose.yml`, `.env.example`, `backend/.env.example`
- Test: `backend/tests/test_chat_primary_hook.py`

- [x] **Step 1: Write failing API tests**

```python
@pytest.mark.asyncio
async def test_primary_selected_does_not_call_legacy(monkeypatch):
    from app.api.v1 import chat as chat_api
    from app.services import semantic_primary

    monkeypatch.setenv("SEMANTIC_PRIMARY_ENABLED", "true")
    monkeypatch.setenv("SEMANTIC_PRIMARY_PERCENT", "100")
    monkeypatch.setattr(chat_api, "route_chat", AsyncMock(side_effect=AssertionError("legacy called")))
    monkeypatch.setattr(semantic_primary, "run_primary_turn", AsyncMock(return_value={"reply": "semantic", "session_id": "s1", "data": {"primary": {"status": "answered"}}}))
    out = await chat_api.chat(body=chat_api.ChatRequest(query="你好", session_id="s1"), db=AsyncMock(), _user=None)
    assert out["reply"] == "semantic"


@pytest.mark.asyncio
async def test_primary_internal_failure_falls_back(monkeypatch):
    from app.api.v1 import chat as chat_api
    from app.services import semantic_primary

    monkeypatch.setenv("SEMANTIC_PRIMARY_ENABLED", "true")
    monkeypatch.setenv("SEMANTIC_PRIMARY_PERCENT", "100")
    monkeypatch.setattr(semantic_primary, "run_primary_turn", AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(chat_api, "route_chat", AsyncMock(return_value={"reply": "legacy", "session_id": "s1", "data": {}}))
    out = await chat_api.chat(body=chat_api.ChatRequest(query="你好", session_id="s1"), db=AsyncMock(), _user=None)
    assert out["reply"] == "legacy"
```

- [x] **Step 2: Run and verify RED**

Run: `python -m pytest -q tests/test_chat_primary_hook.py`
Expected: FAIL because primary integration does not exist.

- [x] **Step 3: Add primary run interface**

Implement `primary_enabled`, `primary_percent`, `primary_selected`, and `run_primary_turn` in `semantic_primary.py`. `run_primary_turn` ensures a session ID, composes the turn, persists it, and returns the canonical chat response.

- [x] **Step 4: Integrate before route_chat**

In `chat.py`, resolve the session ID and owner first. If primary is selected, try `run_primary_turn`; return it on success. On a system exception, record a privacy-minimized fallback marker and continue to `route_chat`. Do not fall back for formal clarify, abstain, refuse, abuse, or out-of-domain results.

- [x] **Step 5: Add configuration and verify GREEN**

Pass the two primary variables through Compose and both env examples. Run:

`python -m pytest -q tests/test_chat_primary_hook.py tests/test_chat_shadow_hook.py tests/test_canary_routing.py`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add backend/app/api/v1/chat.py backend/app/services/semantic_primary.py docker-compose.yml .env.example backend/.env.example backend/tests/test_chat_primary_hook.py
git commit -m "feat: route chat through semantic primary"
```

## Task 6: Staging Matrix And Multi-Topic Memory

**Files:**
- Create: `backend/scripts/run_staging_primary_matrix.py`
- Test: `backend/tests/test_staging_primary_matrix.py`
- Report: `报告/阶段10-语义主路径staging验收.md`

- [x] **Step 1: Write failing query-plan tests**

```python
def test_primary_query_plan_covers_required_routes():
    from scripts.run_staging_primary_matrix import build_primary_query_plan

    plan = build_primary_query_plan([{"enterprise_id": "e1", "name": "企业1"}])
    categories = {item["category"] for item in plan}
    assert {"analysis", "greeting", "capability", "weather", "refusal", "multilingual"}.issubset(categories)
    assert len(plan) >= 30
```

- [x] **Step 2: Run and verify RED**

Run: `python -m pytest -q tests/test_staging_primary_matrix.py`
Expected: FAIL because the matrix script does not exist.

- [x] **Step 3: Implement the matrix runner**

The script must require `STAGING_CONFIRM=true`, require primary enabled at 100%, call the real `/api/v1/chat` endpoint, validate `data.primary.fallback=false`, verify persisted session history, and produce a JSON summary. It must generate at least 30 distinct queries across all required categories.

- [x] **Step 4: Add the six-turn memory case**

Run one session with analysis, weather, greeting, analysis, abuse, then an N-2 reference. Verify the final response references the intended earlier topic and that all six turns are present in session history and topic storage.

- [x] **Step 5: Run staging and commit**

Run the matrix in the isolated `mingjian-staging` project. If any case fails, fix the category root cause and rerun a fresh 30-case set.

```bash
git add backend/scripts/run_staging_primary_matrix.py backend/tests/test_staging_primary_matrix.py 报告/阶段10-语义主路径staging验收.md
git commit -m "test: validate semantic primary on staging"
```

## Task 7: Retirement Audit And Full Verification

**Files:**
- Modify: `docs/superpowers/plans/2026-09-16-mingjian-semantic-rag-v2.md`
- Modify: `报告/语义RAG预发布与影子评估部署手册.md`
- Modify: `红线要求.md`
- Report: `报告/阶段10-语义主路径最终审计.md`

- [x] **Step 1: Update operational documentation**

Document primary enablement, rollback, fallback-only-on-error, the 30-case gate, and the fact that legacy deletion remains blocked until `safe_to_retire=true`.

- [x] **Step 2: Run targeted primary tests**

Run: `python -m pytest -q tests/test_rollout.py tests/test_non_analysis_replies.py tests/test_semantic_primary.py tests/test_semantic_turn_persistence.py tests/test_chat_primary_hook.py tests/test_staging_primary_matrix.py`
Expected: all pass.

- [x] **Step 3: Run full backend regression**

Run: `python -m pytest -q --tb=short`
Expected: 0 failures.

- [x] **Step 4: Run staging HTTP matrix and real PDF report**

Expected: 30/30 semantic primary cases pass, no unexpected fallback, memory case passes, and downloaded report begins with `%PDF-`.

- [x] **Step 5: Run retirement audit**

Run: `python -m scripts.audit_legacy_retirement --shadow-gate-passed --json`
Expected before production primary stabilization: `safe_to_retire=false`. Do not delete legacy until this becomes true after the separately gated rollout.

- [x] **Step 6: Commit final evidence**

```bash
git add docs/superpowers/plans/2026-09-16-mingjian-semantic-rag-v2.md 报告/语义RAG预发布与影子评估部署手册.md 报告/阶段10-语义主路径最终审计.md 红线要求.md
git commit -m "docs: record semantic primary verification"
```

## Self-Review Checklist

- [x] Every route kind in the design has a concrete handler or orchestration path.
- [x] `not_applicable` is a contract error, not a normal response.
- [x] Legacy fallback never handles formal clarify, abstain, refusal, abuse, or out-of-domain outcomes.
- [x] Every primary turn has one writer for session history and topic memory.
- [x] The primary selector is fail-safe and default-off.
- [x] Staging testing uses real HTTP and real anonymized data.
- [x] Full regression and real report PDF verification are explicit gates.
- [x] Legacy deletion remains blocked until retirement audit passes.

