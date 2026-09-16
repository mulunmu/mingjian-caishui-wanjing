# Report Blueprint V1 Validation

Date: 2026-09-16

## Implemented

- Report scope, section, block, and blueprint schemas.
- Compilation into per-chapter tool plans.
- Validation of chapter tools, tool IDs, parameters, dependencies, and blocks.
- Deterministic execution through the existing plan executor.
- Persistent blueprint storage in PostgreSQL-compatible SQLAlchemy tables.
- Blueprint reload and rerun by ID.

## Safety Boundary

The blueprint does not allow the model to generate the entire report body.
The model can only propose a typed blueprint. Each section executes its declared
tools, and claims remain isolated inside that section.

## Verified

- Empty blueprints are rejected.
- Unknown chapters are rejected.
- Blocks cannot reference tools outside their section.
- Duplicate sections and duplicate chapters are rejected.
- Repeated execution produces identical claims.
- Claims do not leak across chapters.
- Blueprint persistence round-trips through the database.
- Loaded blueprints can be compiled and executed again.

## Evidence

```text
5 Blueprint unit tests passed
6 PostgreSQL integration tests passed
Full backend suite: 1127 passed, 12 skipped, 0 failed
```