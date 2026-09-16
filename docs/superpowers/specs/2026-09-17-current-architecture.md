# Current Architecture After Stage 14

Date: 2026-09-17
Status: verified candidate

## Request Path

```text
HTTP /api/v1/chat
-> optional LangGraph outer state machine
-> semantic primary
-> DialogAct + SemanticFrame
-> validated dialogue composition plan
-> Tool RAG candidates
-> ToolPlan
-> AsyncDagRuntime inner execution
-> deterministic Claims
-> finance review / hallucination guard
-> narration and polish
-> final guard
-> response + session/topic persistence
```

LangGraph is optional and disabled by default. It owns only outer control flow:
checkpointing, interrupts, resume and future cyclic workflows. The deterministic
financial execution path remains `AsyncDagRuntime` and is not replaced by
LangGraph.

## Dialogue Composition

Every semantic-primary turn builds and validates:

```text
intent module -> policy module -> content module -> synthesis module
```

Supported intents include analysis, memory, report, knowledge, social, clarify
and refusal. Multi-intent requests separated by semicolons are executed as
sub-turns and persisted as one combined topic/answer. Claims are merged without
regenerating numbers.

## Memory

Conversation state has three layers:

1. Recent turns in `session_store`.
2. Durable topic summaries in `conversation_topic`.
3. Compact memory context containing entity/filter indexes, Claim IDs, tool
   plan references and report IDs.

Absolute references such as `第10个问题` resolve to turn 10. Relative references
such as `往前10轮` resolve ten topics back. Cross-topic follow-ups use durable
topic memory rather than a second state store.

## Reports

Reports are assembled from chapter and block contracts:

- `metric_paragraph`
- `comparison_paragraph`
- `trend_paragraph`
- `synthesis_paragraph`

The shared `blocks` tree is persisted in the report snapshot, rendered by the
PDF HTML template, returned by API detail and consumed by the frontend. The
chapter/block matrix currently validates 31 compatible combinations.

## Optional Dependencies

Core dependencies are pinned in `backend/requirements.txt`. LangGraph is pinned
separately in `backend/requirements-orchestration.txt` and installed only when
the image is built with `INSTALL_ORCHESTRATION=true`.

## Truth Boundary

LLMs never own numeric facts, enterprise lists, threshold outcomes, risk grades
or final report structure. They only propose typed structures or narrate
deterministic Claims. RAG selects validated candidates; registries decide what
is available; executors and guards decide what is true.
