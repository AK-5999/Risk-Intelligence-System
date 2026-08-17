# Stretch — Next Week Plan

If I had one additional week, I would focus on **generalization and robustness** rather than adding new product features.

## 1. Test on a Second Annual Report

Run the complete Phase 1 → Phase 2 pipeline on an annual report from another company.

This would validate whether the current canonical schema and deterministic risk extraction logic generalize beyond the report used for development.

## 2. Expand the Evaluation Set

Increase the current Phase 2 generalization suite with cases covering:

* alternative table structures;
* different terminology for risks and opportunities;
* different materiality wording;
* ambiguous risk/opportunity statements;
* missing or incomplete fields.

The goal would be to understand failure modes rather than optimize only for the current golden set.

## 3. Reduce Report-Specific Assumptions

Move remaining assumptions such as known page ranges and section terminology into configurable discovery rules.

This would make the pipeline less dependent on a particular annual-report structure.

## 4. Improve Visual Content Handling

Experiment with extraction of information currently difficult for the parser, particularly:

* charts;
* diagrams;
* maps;
* visual-only disclosures.

A vision model could be selectively introduced only when deterministic parsing cannot recover useful content.

## 5. Add End-to-End Regression Tests

Create a single automated evaluation command that runs:

```text
Parsing
   ↓
Risk Extraction
   ↓
Golden-Set Evaluation
   ↓
Generalization Tests
   ↓
Hardcoding Guard
```

This would make future changes easier to validate and prevent regressions.

## End-of-Week Goal

By the end of the additional week, I would aim to demonstrate:

> **The same architecture working on more than one annual report, with broader evaluation coverage and fewer report-specific assumptions.**

This would provide stronger evidence that the PoC is evolving from a successful single-report pipeline toward a reusable Risk Intelligence System.
