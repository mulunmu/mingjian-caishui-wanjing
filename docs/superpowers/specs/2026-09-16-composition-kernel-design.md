# Composition Kernel And Async Runtime Design

Date: 2026-09-16
Status: Approved direction; implementation plan follows

## Goal

Represent hundreds or thousands of useful dialogue and report combinations
without enumerating each combination as a route. The system will compose typed
modules into validated DAG plans and execute independent nodes asynchronously.

## Non-Goals

- Do not store every possible combination as a route or RAG record.
- Do not let an LLM execute arbitrary tools or decide numeric facts.
- Do not replace `session_store` or `topic_memory` with a second state store.
- Do not make LangGraph a mandatory dependency for the first implementation.

## Architecture Layers

```text
Policy Route
-> Semantic Frame
-> Skill / Module RAG
-> Composition Planner
-> Validated Composition DAG
-> Async DAG Runtime
-> Claims / Blocks / Reply
-> Finance Review
-> Deterministic Guard
-> Narration And Polish
-> Final Guard
```

### Policy Route

The existing route kinds remain coarse safety and response-policy classes. They
decide whether to analyze, clarify, refuse, redirect, socialize, or switch
language. They are not the complete intent taxonomy.

### Semantic Frame

The semantic frame records:

- speech act,
- business domain,
- task type,
- subject scope,
- entities and metrics,
- filters and time range,
- requested output,
- references and memory intent,
- safety and language,
- missing slots and confidence.

### Module Registry

Every atomic module has typed ports and an execution contract:

```text
module_id
kind
version
status
inputs
outputs
requires
constraints
cost
side_effect
permissions
```

Module kinds include metric, operator, threshold, knowledge, chapter, block,
action, and verifier.

### Composition Planner

The planner receives a semantic frame, retrieved modules, and reusable patterns.
It proposes a DAG, but cannot execute it. The plan consists of nodes, bindings,
edges, and output requirements.

### Plan Validator

Validation is deterministic and checks:

- module existence and version,
- type compatibility,
- required inputs,
- dependency availability,
- DAG cycles,
- permissions and side effects,
- cost and node limits,
- required output coverage.

### Async DAG Runtime

Independent nodes execute concurrently with bounded concurrency. Dependencies
execute only after their inputs are available. Every node has timeout, retry,
fallback, idempotency, and cache metadata.

## Composition Rules

There are three reusable levels:

```text
atom: metric_debt_ratio
pattern: metric + threshold + comparison
generated plan: concrete DAG bound to enterprise and filters
```

Patterns are reusable structure, not frozen combinations. A generated plan is
saved only as a Blueprint or execution trace when needed for reproducibility.

## Async Execution Rules

- Retrieval nodes for skills, modules, and knowledge run in parallel.
- Independent metric and data nodes run in parallel.
- Report chapters run in parallel.
- Blocks inside a chapter may run in parallel when they do not depend on one another.
- Finance review, deterministic validation, and narration run only when their
  required Claims are complete.
- Language polish is serial and followed by a final deterministic guard.
- All external calls use bounded concurrency and timeouts.

## Persistence

The existing session and topic stores remain the state source. Composition
execution records privacy-minimized node status and may persist a validated
Blueprint for reports.

## Rollout

Composition Kernel runs behind a feature flag and initially enables only a small
set of validated patterns. The semantic primary path remains the dialogue
entrypoint. Legacy remains an internal-error fallback until retirement gates pass.

## Acceptance

```text
typed module registry validates all seeded modules
invalid port and dependency plans never execute
valid plans execute deterministically
independent nodes demonstrably run concurrently
timeouts and cancellation leave consistent state
at least 60 modules or skills are retrievable
multi-step plans cover metric + threshold + comparison and report chapter cases
full backend regression has zero failures
```
