# Semantic Primary Design

Date: 2026-09-16
Status: Approved in thread; pending written-spec review

> Superseded 2026-09-17: Stage 9 completed production rollout and deleted the
> legacy package. The active endpoint now fails closed instead of falling back.

## Goal

Make the semantic dialogue path the primary response path for every supported
conversation type. The legacy router remains only as an internal-error fallback
until semantic primary has passed staging and production observation gates.

This stage does not remove the legacy path. It makes the conditions for eventual
retirement measurable and real.

## Non-Goals

- Do not make `SEMANTIC_CANARY_PERCENT=100` stand in for semantic primary.
- Do not let an LLM decide facts, thresholds, entities, or report contents.
- Do not remove `route_chat` or soft-fallback regexes in this stage.
- Do not add voice, mobile OS integration, or new report features.
- Do not create a second dialogue state store outside `session_store` and
  `topic_memory`.

## Architecture

```text
HTTP chat request
-> semantic-primary selector
-> independent DialogAct route
-> ConversationPolicy
-> semantic route handler
   -> tool execution for analysis/report
   -> deterministic strategy for non-analysis
-> session history persistence
-> topic-thread persistence
-> canonical chat response
```

The legacy route is invoked only when semantic primary cannot produce a valid
business result because of an internal failure.

## Activation And Rollback

Two configuration values control the stage:

```env
SEMANTIC_PRIMARY_ENABLED=false
SEMANTIC_PRIMARY_PERCENT=0
```

Rules:

- `SEMANTIC_PRIMARY_ENABLED=false` keeps legacy as the response path.
- When enabled, selection is deterministic by `session_id`.
- `SEMANTIC_PRIMARY_PERCENT=100` selects all sessions.
- Semantic primary takes precedence over canary configuration when enabled.
- Setting `SEMANTIC_PRIMARY_ENABLED=false` and restarting backend is the rollback
  path. No database rollback is required.
- Invalid or non-finite percentages are treated as `0`.

## Route Coverage

Every route must return a valid response without legacy fallback:

```text
analysis
report
greeting
capability
product_faq
feedback
out_of_domain
abuse
language_switch
unknown_entity
clarify
refuse
```

### Analysis And Report

Analysis continues through:

```text
Tool RAG
-> ToolPlan validation
-> deterministic executor
-> Claims
-> narration
-> hallucination guard
```

Report requests call the existing report/custom-report services. The semantic
layer may choose the report structure, but it may not generate a whole report as
free text.

### Non-Analysis

Non-analysis responses use deterministic policy handlers:

- `greeting`: short social response, no tools.
- `capability`: answer from the capability registry.
- `product_faq`: answer from the controlled FAQ knowledge source.
- `feedback`: acknowledge feedback without inventing product changes.
- `out_of_domain`: abstain and redirect to supported financial-risk topics.
- `abuse`: de-escalate and return to supported tasks.
- `language_switch`: preserve language intent and route the underlying request.
- `unknown_entity`: request a valid enterprise name or identifier.
- `clarify`: request the missing entity, metric, scope, or business domain.
- `refuse`: reject fabrication, forgery, or data invention.

These outcomes are valid business results and must never trigger legacy fallback.

## Response Contract

The existing chat response shape remains stable. Semantic-primary responses add:

```json
{
  "data": {
    "primary": {
      "status": "answered",
      "route": "greeting",
      "domain": null,
      "fallback": false,
      "fallback_reason": null
    }
  }
}
```

`reply`, `reply_source`, `claims`, `followups`, and `followup_items` retain their
existing meanings.

## Session And Topic Persistence

Every successful semantic-primary business result is persisted before the HTTP
response is returned:

- Append the user/assistant turn through `session_store`.
- Store route-derived intent, function, dimension, and claim/follow-up metadata.
- Append a `ConversationTopic` record for every turn, including non-analysis.
- Store a deterministic summary and normalized entities/filters, not hidden
  chain-of-thought or unnecessary raw prompt text.

If persistence fails, semantic primary does not return an unbacked answer. It
falls back to legacy and records a privacy-minimized persistence failure.

## Fallback Policy

Legacy fallback is allowed only for:

- semantic orchestration exception,
- route/composer system error,
- session or topic persistence failure,
- data access failure that prevents a valid response.

The following are not fallback triggers:

```text
clarify
abstain
refuse
out_of_domain
unknown_entity
abuse
```

`not_applicable` must be eliminated from the primary path because every supported
route has an explicit policy. If it is returned unexpectedly, treat it as a
primary-contract error, record a privacy-minimized reason, and allow legacy
fallback rather than exposing an empty response.

## Observability

Record privacy-minimized primary observations:

- selected primary percentage,
- route and domain,
- status,
- fallback flag and reason,
- latency,
- persistence success,
- claim count.

User text is not stored in primary observation records.

## Compatibility

- The HTTP response contract remains backward compatible.
- `SEMANTIC_CANARY_PERCENT` remains available for legacy-comparison rollout but
  is bypassed when semantic primary is enabled.
- Existing shadow tables remain readable and are not deleted.
- No database migration is required unless implementation needs a new index.

## Test Strategy

### Unit And Integration

- Selection is deterministic and fail-safe at 0 and 100 percent.
- All 12 route kinds return a formal result without legacy fallback.
- Analysis remains deterministic and anchored to Claims.
- Every primary turn creates session history and a topic-thread record.
- Formal `clarify`, `refuse`, and `out_of_domain` responses do not call legacy.
- Internal exceptions fall back to legacy and expose no internal error text.
- Persistence failure falls back without returning an unbacked response.
- Long conversations resolve N-1, N-2, and cross-topic follow-ups.

### Staging

- Run a 100% semantic-primary matrix with at least 30 distinct real queries.
- Include analysis, report, greeting, capability, weather, abuse, multilingual,
  unknown-entity, refusal, and clarification cases.
- Run a multi-topic session with at least six turns and verify rollback behavior.
- If any run fails, fix the category root cause and run a new 30-case set.

### Regression

- Full backend suite passes.
- Real staging chat and PDF report paths pass.
- Retirement audit is rerun.
- Production rollout remains separately gated; no legacy files are deleted
  until `safe_to_retire=true`.

## Acceptance Criteria

```text
primary route coverage=12/12
formal result without fallback=100%
unexpected legacy fallback=0
session persistence=100%
topic persistence=100%
unanchored numbers=0
staging matrix=30 distinct queries pass
multi-topic rollback tests pass
full backend regression=0 failures
report end-to-end PDF pass
```

## Delivery Sequence

1. Add the primary selector and feature flags with default-off behavior.
2. Add all non-analysis policy handlers.
3. Add business-result and persistence guarantees.
4. Run the staging 30-case matrix and memory session.
5. Run full regression and report end-to-end checks.
6. Run retirement audit. Legacy deletion remains blocked until semantic primary
   is stable and `safe_to_retire=true`.

## Risks And Controls

- Non-analysis flexibility could become uncontrolled generation: use
  deterministic handlers and controlled knowledge sources.
- Report routing could bypass report safeguards: call existing report services
  and preserve chapter/tool boundaries.
- Duplicate persistence could corrupt history: one primary turn writer, with
  idempotent turn identity.
- A rollout flag could strand sessions: selection is session-sticky and rollback
  is a full feature disable.
