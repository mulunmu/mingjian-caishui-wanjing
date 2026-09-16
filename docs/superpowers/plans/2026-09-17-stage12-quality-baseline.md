# Stage 12: Quality Baseline And Block Report Composition

## Goal

Validate the completed semantic, RAG, memory, composition, email, and report
systems against real HTTP scenarios. Improve report generation from chapter-level
assembly to paragraph-block assembly without letting an LLM generate the whole report.

## Stage 12A: Dialogue And RAG Quality

- Build a 100+ case live HTTP matrix.
- Cover analysis, multi-metric requests, reports, greeting, capability, FAQ,
  out-of-domain, refusal, abuse, multilingual, unknown entity, clarification,
  and six-turn N-2 memory.
- Require no fallback, no empty replies, valid routes/statuses, Claims for analysis,
  report metadata for reports, and persisted history.
- Record pass rate, P50 and P95 latency.

Acceptance:

```text
total >= 100
failed = 0
fallback count = 0
N-2 memory = passed
```

## Stage 12B: Block-Level Report Composition

Report IR becomes:

```text
Report
-> Chapters
-> Blocks
-> metric paragraphs + synthesis paragraph
-> HTML/PDF renderer
```

Rules:

- A metric Claim becomes an independent paragraph block.
- A chapter narration becomes a synthesis block, not the whole report.
- PDF and frontend render the same block list.
- Technical trace stays in the API snapshot and never appears in user-facing HTML/PDF.
- Existing chapter tables and charts remain available.

Acceptance:

```text
custom chapter combinations generate successfully
each chapter has metric blocks
PDF magic = %PDF-
no internal table names in user-visible HTML
```

## Stage 12C: Production Stabilization

- Run full regression and production HTTP matrices.
- Verify asynchronous latency and partial failure behavior.
- Verify report email delivery and EmailLog.
- Freeze the Stage 12 baseline.

