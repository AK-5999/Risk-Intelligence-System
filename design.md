# Risk Intelligence System — Technical Design

## 1. Architecture Overview

The implementation is decomposed into two major phases:

```text
Annual Report PDF
        │
        ▼
┌──────────────────────────┐
│ Phase 1                  │
│ Parsing + Normalization  │
└──────────────────────────┘
        │
        ▼
Canonical Document JSON
        │
        ▼
┌──────────────────────────┐
│ Phase 2                  │
│ Risk Intelligence        │
└──────────────────────────┘
        │
        ▼
Structured Risk JSON
        │
        ▼
Evaluation
```

The central design principle is separation of concerns.

Phase 1 answers:

> **What information exists in the document, where is it, and how is it structured?**

Phase 2 answers:

> **Which of that information represents a relevant risk, and how should it be normalized into the product schema?**

This prevents downstream risk logic from becoming tightly coupled to a specific PDF parsing library.

---

# 2. Technology Choices

The PoC primarily uses:

* **Python** for pipeline implementation;
* **Docling** for PDF parsing and layout-aware extraction;
* **JSON** as the intermediate representation;
* **SHA-256** for document identity;
* **Pydantic** for structured schema validation;
* **LLM structured generation** for bounded semantic transformation;
* deterministic Python logic for filtering, provenance, validation, and evaluation;
* versioned prompts for reproducible LLM behavior.

The stack intentionally remains lightweight because correctness and inspectability are more important than infrastructure complexity at this stage.

---

# 3. Phase 1 — Parsing and Canonical Representation

## Parsing Approach

Phase 1 uses a two-stage approach:

```text
PDF
 │
 ▼
Docling Parsing
 │
 ▼
Raw Parser Representation
 │
 ▼
Normalization Layer
 │
 ▼
Canonical Document JSON
```

Docling handles layout-aware PDF processing, while the normalization layer converts parser-specific output into a stable internal representation.

The canonical representation preserves information such as:

* page number;
* content type;
* text;
* headings;
* tables;
* bounding boxes;
* structural relationships;
* provenance.

This allows downstream components to operate on the internal schema rather than Docling-specific objects.

## Spatially Agnostic Downstream Design

Spatial information is important during parsing because bounding boxes help reconstruct relationships between text, table cells, headings, and other page elements.

However, raw spatial coordinates are not treated as the permanent business representation.

The design is therefore:

```text
PDF Geometry
     ↓
Relationship Reconstruction
     ↓
Canonical Semantics
     ↓
Risk Intelligence
```

This keeps the downstream risk model spatially agnostic while still benefiting from layout information during ingestion.

## Incremental Processing

Selected pages can be persisted incrementally rather than requiring the entire document to be rebuilt after every experiment.

Document identity is tracked using SHA-256, and page-level processing supports controlled merge/replace behavior.

This was particularly useful during the PoC because parsing strategies could be tested against selected difficult pages without repeatedly processing the complete report.

---

# 4. Phase 2 — Risk Intelligence

Phase 2 deliberately separates **risk discovery**, **semantic generation**, and **validation**.

```text
Canonical Document
       │
       ▼
RiskAnalyzer
       │
       ▼
RiskCandidateExtractor
       │
       ▼
Deterministic Candidates
       │
       ▼
RiskGenerator
       │
       ▼
Hybrid Category Resolution
       │
       ▼
Pydantic Validation
       │
       ▼
Final Structured Risks
```

## RiskAnalyzer

`RiskAnalyzer` identifies relevant normalized source structures from the canonical document.

The analyzer does not ask an LLM to search the entire annual report.

Instead, it exposes bounded evidence structures for downstream processing.

This reduces prompt size, improves traceability, and avoids allowing an LLM to invent risks from unrelated report content.

## RiskCandidateExtractor

Candidate extraction is deterministic.

The extractor identifies qualifying risk entries based on normalized source semantics rather than maintaining a list of expected Vestas risk answers.

Examples of deterministic behavior include:

* retaining explicitly declared enterprise principal-risk columns;
* retaining material financial risks;
* excluding opportunities;
* excluding immaterial entries;
* preventing environmental impact statements alone from automatically becoming financial risks.

The extractor is therefore **schema-generic rather than report-answer-hardcoded**.

It is not claimed to be universally compatible with every annual-report schema.

---

# 5. Bounded LLM Generation

After deterministic candidate discovery, candidates are grouped into bounded contexts based on source type, section, and topic.

The LLM receives only the information required for semantic generation.

Its responsibilities are intentionally limited to:

* concise risk title generation where the title is not explicitly provided by the source;
* grounded 2–3 sentence descriptions;
* semantic category classification.

The LLM does **not** decide whether an arbitrary report statement should become a risk.

Enterprise risk titles that are explicitly provided by source table headers are attached deterministically rather than allowing the model to rename them.

Likewise, source page, section, mitigation, and block references are attached from deterministic candidate metadata rather than generated by the LLM.

---

# 6. Hybrid Category Resolution

An important refinement introduced during evaluation is that the LLM is not always the final authority for category assignment.

Category resolution follows:

```text
Strong Source Taxonomy?
        │
      Yes
        ▼
Deterministic Category
        │
       No
        ▼
Valid LLM Category?
        │
      Yes
        ▼
Keep LLM Category
        │
       No
        ▼
Deterministic Semantic Fallback
```

For example, when the source explicitly identifies a disclosure under a strong climate taxonomy, that evidence can take precedence over an LLM interpretation that focuses only on the regulatory mechanism of the risk.

This avoids title-specific hardcoding while using stronger evidence already present in the source document.

Generic semantic rules may still contain terms such as `cyber`, `execution`, `operational`, or `corruption`. These are reusable taxonomy signals rather than expected report answers.

---

# 7. Validation and Guardrails

Generated responses are validated through Pydantic models.

The generation contract checks:

* every candidate is returned;
* no unexpected candidate ID is introduced;
* candidate IDs are unique;
* required fields are present;
* categories belong to the canonical enum;
* descriptions satisfy the expected sentence constraint.

Source metadata is attached after semantic generation.

This produces the pattern:

```text
Deterministic Evidence
        ↓
Bounded LLM Transformation
        ↓
Deterministic Resolution
        ↓
Schema Validation
        ↓
Deterministic Provenance Attachment
```

This decomposition limits the blast radius of LLM variability.

LLM/API failures, including rate limits or invalid structured responses, remain possible and are treated as bounded generation-layer failures rather than corrupting the deterministic extraction stages.

---

# 8. Evaluation Design

Evaluation is maintained separately from production extraction logic.

## Phase 1 Evaluation

Phase 1 uses a manually verified page-level golden set covering representative document structures.

The evaluation demonstrated stronger performance on:

* narrative text;
* multi-column layouts;
* structured tables;
* financial and sustainability data.

The primary known weakness is visual-only semantic content such as:

* maps;
* diagrams;
* complex infographics.

These limitations are documented rather than hidden.

## Phase 2 Golden-Set Evaluation

Phase 2 compares final generated risks against independently maintained expected risk records.

For risk presence:

```text
Generated ∩ Golden
        ↓
True Positives

Golden - Generated
        ↓
False Negatives

Generated - Golden
        ↓
False Positives
```

Therefore:

```text
Precision = TP / (TP + FP)

Recall = TP / (TP + FN)

F1 = 2 × Precision × Recall
     ─────────────────────
      Precision + Recall
```

A significant evaluation improvement was separating **false-positive detection** from the known failure catalogue.

Previously known failure cases could influence which outputs were treated as false positives. The evaluator now derives false positives from **all generated risks absent from the golden set**.

`failure_cases.json` remains useful only for diagnostic analysis of known failure modes.

---

# 9. Generalization Evaluation

A separate synthetic evaluation checks whether deterministic extraction behavior generalizes beyond memorized report answers.

Current cases test whether the extractor can:

1. retain a generic financial risk;
2. exclude a financial opportunity;
3. exclude an immaterial financial entry;
4. avoid interpreting an environmental impact alone as a financial risk.

This test complements the report-specific golden set.

The golden set answers:

> Did the system correctly process this report?

The generalization suite answers:

> Is the extraction logic based on reusable schema semantics rather than memorized answers?

Both are necessary.

---

# 10. Hardcoding Guard

A dedicated hardcoding guard checks production source code for report-specific expected risk titles.

Instead of manually maintaining a partial list, forbidden titles are derived directly from:

```text
golden_set.json
       ↓
Expected Risk Titles
       ↓
Production Source Scan
       ↓
PASS / FAIL
```

The guard scans the production extraction/generation path while excluding evaluation fixtures and prompts that legitimately contain expected terminology.

Generic taxonomy keywords are permitted because they represent reusable semantic rules.

Exact golden-set risk answers embedded into production extraction logic are not.

This creates a useful separation between:

```text
Generic domain knowledge     → allowed

Expected evaluation answers  → prohibited
```

---

# 11. Key Trade-offs

### Correctness vs. Coverage

The PoC prefers explicit evidence and conservative extraction over maximizing the number of generated risks.

This can reduce coverage on unfamiliar report structures but decreases unsupported outputs.

### Deterministic Logic vs. LLM Reasoning

Deterministic logic is used where rules can be expressed reliably:

* structural extraction;
* materiality filtering;
* opportunity exclusion;
* provenance;
* strong source taxonomy;
* validation;
* evaluation.

LLMs are used where semantic transformation provides value:

* concise descriptions;
* title normalization where necessary;
* category interpretation where deterministic source evidence is insufficient.

### Parser-Specific Accuracy vs. Architectural Flexibility

Docling provides useful PDF structure, but downstream code does not consume Docling objects directly.

The normalization layer introduces additional implementation work but prevents parser lock-in.

### Universal Layout Support vs. PoC Reliability

The current system makes explicit assumptions about normalized annual-report structures.

Attempting universal layout understanding in this first slice would substantially increase complexity and reduce the ability to evaluate correctness rigorously.

### LLM Flexibility vs. Reproducibility

LLMs provide useful semantic normalization but introduce variability, API failures, and rate-limit dependencies.

Structured schemas, bounded contexts, prompt versioning, deterministic validation, and source-derived metadata reduce this risk.

---

# 12. Known Limitations

The current PoC does not fully solve:

* visual-only semantics in maps and complex diagrams;
* arbitrary annual-report schemas;
* alternative table orientations;
* unknown terminology for opportunities or materiality;
* ambiguous risk/opportunity statements in the same source field;
* OCR-heavy or severely corrupted documents;
* cross-report taxonomy normalization;
* year-over-year risk matching;
* production-scale throughput and API resilience.

These limitations are intentionally documented as boundaries of the current evidence rather than hidden behind the successful golden-set metrics.

---

# 13. Future Architecture

The current output can later feed a broader risk-intelligence platform:

```text
Multiple Corporate Reports
          │
          ▼
Document Ingestion
          │
          ▼
Canonical Document Layer
          │
          ▼
Risk Extraction
          │
          ▼
Risk Database
          │
     ┌────┴─────┐
     ▼          ▼
 Retrieval    YoY Matching
     │          │
     └────┬─────┘
          ▼
 Risk Intelligence
          │
     ┌────┼────────┐
     ▼    ▼        ▼
 Search  Alerts   Analyst UI
```

Future work would therefore focus on broader document generalization, database-backed risk identity, cross-year comparison, emerging-risk detection, retrieval, and analyst-facing product surfaces.

---

# 14. Design Principle

The implementation can be summarized by one principle:

> **Preserve evidence deterministically, use AI selectively for semantic interpretation, and validate everything that becomes product data.**

Phase 1 establishes reliable document evidence.

Phase 2 transforms that evidence into structured risk intelligence.

The evaluation layer verifies both correctness and the absence of report-answer hardcoding.

This separation provides a foundation that can evolve from a single-report PoC into a broader risk-intelligence product without requiring the core pipeline to be redesigned.
