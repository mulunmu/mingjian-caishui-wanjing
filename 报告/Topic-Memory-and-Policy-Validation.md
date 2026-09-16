# Topic Memory and Conversation Policy Validation

Date: 2026-09-16

## Policy Matrix

- Greeting: no candidate retrieval, no execution.
- Capability/FAQ: capability namespace only.
- Out of domain: redirect, no tools.
- Abuse: de-escalation, no analysis.
- Clarification: candidate retrieval allowed, execution blocked.
- Analysis: candidate retrieval and execution allowed after plan validation.
- Report: candidate retrieval and report execution allowed.

## Topic Threads

Each topic stores:

- session and turn order
- parent topic
- summary
- entities and filters
- scenario and intent
- tool plan and claim references
- active/completed status

Validated behavior:

- N-1 rollback.
- N-2 rollback.
- Semantic back-reference after unrelated topics.
- Cross-topic follow-up merges old entities/filters with the current intent.
- Referencing an old topic does not change the active topic unless rollback is
  explicitly requested.

## Shadow Path

The shadow path performs:

```text
raw model route
-> deterministic normalization
-> policy resolution
-> validated Tool RAG candidate retrieval
```

It is read-only and does not replace `chat_router`.

## Evidence

```text
11 stage-specific tests passed
4 PostgreSQL integration tests passed
Full backend suite: 1115 passed, 10 skipped, 0 failed
```
