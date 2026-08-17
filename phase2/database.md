# Phase 2 – Risk Identification, Context Construction and Structured Risk Generation

## Overview

Phase 1 established a reliable, parser-independent representation of the annual report.

The output of Phase 1 is a **Canonical Document JSON** containing normalized textual and tabular content together with page-level provenance.

Phase 2 moves from **document understanding** to **risk intelligence generation**.

The primary objective is:

> **Can structured risk information be identified and generated from the normalized annual-report content while preserving the relationship between the generated risk and its original source evidence?**

The important architectural principle in this phase is that the LLM should **not search the complete annual report blindly**.

Instead, deterministic processing is first used to identify relevant regions, reconstruct the necessary context, and only then provide bounded evidence to the LLM.

---

# Phase 1 → Phase 2 Boundary

Phase 1 produces:

```text
PDF
 │
 ▼
Docling Parser
 │
 ▼
Raw Parser JSON
 │
 ▼
Normalization
 │
 ▼
Canonical Document JSON
```

Phase 2 starts from:

```text
Canonical Document JSON
        │
        ▼
Risk-Relevant Content Detection
        │
        ▼
Context Construction
        │
        ▼
Structured Risk Generation
        │
        ▼
Risk Database
```

Therefore, Phase 2 does not directly depend on Docling.

It depends only on the canonical representation created in Phase 1.

This maintains separation between:

```text
Document Processing
        ↓
Document Understanding
        ↓
Risk Intelligence
```

---

# Research Boundary

The primary Phase 2 research question is:

> **Can principal enterprise risks be reliably identified from canonical annual-report content and converted into structured risk records without losing source traceability?**

The initial scope focuses on:

* Identifying risk-relevant sections
* Identifying ESRS/materiality-related topics
* Associating nearby tables with relevant topics
* Constructing bounded risk contexts
* Generating structured risk objects
* Preserving page and block-level provenance
* Categorizing generated risks
* Preparing generated risks for persistence

The following are not the primary objective of the initial Phase 2 implementation:

* Cross-company risk comparison
* Year-over-year risk evolution
* Risk trend prediction
* Semantic search
* User-facing search APIs
* Risk dashboards
* Automated risk scoring
* Cross-document entity resolution

These capabilities can be introduced after reliable risk extraction is established.

---

# Goal 1 — Risk-Relevant Content Identification

## Problem

The annual report contains hundreds of blocks.

Sending the complete document directly to an LLM would create several problems:

* unnecessary token consumption,
* irrelevant context,
* increased hallucination risk,
* weaker evidence attribution,
* difficulty associating generated risks with exact source blocks.

Therefore, risk generation is divided into multiple stages.

---

## Step 1 — Document Analysis

The first stage analyzes the canonical document and identifies areas likely to contain risk information.

```text
Canonical Document
        │
        ▼
Document Analysis
        │
        ├── Risk Topics
        │
        ├── ESRS Topics
        │
        └── Material Tables
        │
        ▼
risk_analysis.json
```

The analysis stage does **not generate final risks**.

Its responsibility is to determine:

> **Where is the useful risk evidence located?**

This separates **evidence discovery** from **risk reasoning**.

---

# Goal 2 — Topic and Table Association

## Why Table Association Was Required

Risk information is not always represented as continuous narrative text.

In several annual-report sections, information is distributed spatially:

```text
Risk Heading
     +
Description
     +
Nearby Table
```

or:

```text
ESRS Topic
     +
Materiality Table
```

The canonical document preserves:

* page number,
* block identifier,
* block type,
* bounding-box geometry.

This allows related content to be associated without immediately using an LLM.

---

## Geometry-Based Association

Nearby tables are attached to relevant topics using layout information.

The association considers signals such as:

```text
distance
overlap
page position
block relationship
```

Conceptually:

```text
Topic Block
    │
    │ spatial relationship
    ▼
Candidate Table
    │
    ▼
Association Score / Rule
```

The purpose is to reconstruct context that was visually obvious in the PDF but represented as independent blocks after parsing.

---

## Why Deterministic Association First?

An alternative approach would be:

```text
All page blocks
      ↓
LLM
      ↓
Determine relationships
```

This was intentionally avoided where geometry already provides sufficient information.

Using deterministic relationships provides:

* reproducibility,
* lower LLM cost,
* easier debugging,
* explainable associations,
* reduced hallucination opportunities.

The LLM is reserved for semantic reasoning rather than basic layout reconstruction.

---

# Step 1 Output

The first stage writes:

```text
output/risk_analysis.json
```

This intermediate artifact is intentionally persisted.

It allows the analysis stage to be inspected independently from risk generation.

This is useful during debugging because failures can be isolated as:

```text
Document Analysis Problem
```

versus:

```text
Risk Generation Problem
```

instead of rerunning the complete pipeline for every experiment.

---

# Goal 3 — Context Construction

## Why Context Construction Is Required

After identifying relevant topics, the next problem is deciding exactly what evidence should be supplied to the risk-generation model.

The complete annual report should not be used as one prompt.

Instead:

```text
Detected Topic
      │
      ▼
Relevant Blocks
      │
      ├── Heading
      ├── Narrative
      ├── Associated Table
      └── Nearby Evidence
      │
      ▼
Risk Context
```

Each context represents one bounded unit of evidence from which one or more risks may be generated.

---

## Current Context Generation

The analysis identified:

```text
7 topics
8 material tables
```

All identified topics had relevant table associations during the tested run.

The context-building stage produced:

```text
8 risk contexts
```

These contexts were subsequently passed independently to structured risk generation.

---

# Why Contexts Are Generated Separately

Independent contexts provide several advantages.

### Smaller Prompt Size

Only relevant evidence is supplied to the model.

### Better Traceability

Every generated risk can be linked to the context from which it originated.

### Better Failure Isolation

If one context produces poor output, that context can be inspected independently.

### Future Parallelism

Independent contexts can eventually be processed concurrently.

### Easier Evaluation

Risk generation can be evaluated at the context level instead of evaluating one giant document-level response.

---

# Goal 4 — Structured Risk Generation

## LLM Responsibility

The LLM is used only after deterministic evidence preparation.

Its responsibility is semantic interpretation:

```text
Prepared Risk Context
        │
        ▼
Risk Extraction Prompt
        │
        ▼
Structured Risk Objects
```

The current risk-generation prompt is versioned.

Example runtime information:

```text
prompt: risk_extraction
version: 1.0
hash: 1f0b1e5735af
```

Prompt versioning is important because changes to prompts can change generated risks.

Without recording the prompt version, reproducing previous results becomes difficult.

---

# Structured Output Validation

LLM responses are not accepted directly as trusted application data.

They are validated against Pydantic models.

Conceptually:

```text
LLM Response
     │
     ▼
JSON Parsing
     │
     ▼
Pydantic Validation
     │
 ┌───┴────┐
 │        │
Valid   Invalid
 │        │
 ▼        ▼
Accept   Fail / Retry / Log
```

This prevents malformed model output from silently entering downstream storage.

---

# Important Failure — GeneratedRiskBatch Validation

During development, the following class of error occurred:

```text
ValidationError for GeneratedRiskBatch
```

The model returned generated risk information, but the generated object did not match the application schema.

One observed issue was that required fields such as:

```text
category
```

were missing from generated risk objects.

Another failure mode occurred when a risk object was returned as a serialized JSON string rather than as an actual dictionary/object.

Conceptually, the system expected:

```json
{
  "risks": [
    {
      "title": "...",
      "category": "..."
    }
  ]
}
```

but could receive something structurally closer to:

```json
{
  "risks": [
    "{\"title\": \"...\"}"
  ]
}
```

The second representation is a string, not a structured risk object.

---

# Design Lesson

Structured LLM output involves three different contracts:

```text
Prompt Contract
      +
Model Output Contract
      +
Application Schema Contract
```

All three must agree.

It is not enough for the generated text to *look like JSON*.

The returned object must conform exactly to the application's expected schema.

Therefore, schema validation remains mandatory at the boundary between:

```text
Generative AI
      ↓
Application Logic
```

---

# Category Resolution

Risk category handling was separated from raw risk generation.

This avoids relying entirely on the model to produce perfectly normalized category names.

Conceptually:

```text
Generated Risk
      │
      ▼
Category Resolution
      │
      ▼
Canonical Risk Category
```

This creates a controlled taxonomy rather than allowing arbitrary category strings to proliferate throughout the database.

---

# Generated Risk Provenance

Generated risks preserve evidence information such as:

```text
page
section
source_block_ids
```

Example risks generated during testing included:

```text
Geopolitics and regulatory framework
Project execution
Cyber attacks
```

The important requirement is not merely that the system can produce these names.

It must also answer:

> **Where did this risk come from?**

Therefore:

```text
Generated Risk
     │
     ▼
Source Context
     │
     ▼
Canonical Blocks
     │
     ▼
PDF Page
```

This provenance chain is one of the core architectural requirements of the Risk Intelligence System.

---

# Goal 5 — Risk Database

## Why a Risk Database Is Required

Canonical Document JSON represents the **source document**.

Generated risk objects represent **derived intelligence**.

These are fundamentally different data layers.

Therefore, generated risks should not simply be inserted back into the canonical document.

The architecture separates:

```text
Source Knowledge
```

from:

```text
Derived Risk Intelligence
```

Conceptually:

```text
Canonical Documents
        │
        ▼
Risk Intelligence Pipeline
        │
        ▼
Risk Database
```

The Risk Database becomes the structured persistence layer used by future components such as:

* risk search,
* company comparison,
* year-over-year comparison,
* risk evolution analysis,
* emerging-risk detection.

---

# Key Design Principle — Spatial Agnostic Architecture

Phase 1 uses spatial information because PDF understanding requires geometry.

For example:

```text
bounding boxes
page coordinates
block positions
table proximity
```

However, these coordinates describe **how information appeared on a PDF page**.

They should not become the permanent semantic model of the Risk Intelligence System.

Therefore, Phase 2 introduces an important architectural boundary:

> **Use spatial information to reconstruct meaning, but store the reconstructed semantic relationship independently of spatial layout.**

For example:

```text
PDF Representation

Heading at:
x = ...
y = ...

Table at:
x = ...
y = ...
```

may be used to determine:

```text
Heading → describes → Table
```

Once that relationship has been established, downstream risk reasoning should operate on:

```text
Semantic Relationship
```

rather than repeatedly depending on PDF coordinates.

This makes the downstream architecture increasingly **spatial agnostic**.

---

# Why Spatial Agnosticism Matters

Today the source is:

```text
PDF
```

Future sources may include:

```text
DOCX
HTML
XLSX
PPTX
Regulatory APIs
Company filings
Structured databases
```

An architecture permanently dependent on PDF coordinates would make these sources difficult to integrate.

Instead:

```text
Source Format
      │
      ▼
Source-Specific Processing
      │
      ▼
Canonical Semantic Representation
      │
      ▼
Risk Intelligence
```

Only the source-processing layer needs to understand coordinates.

Risk intelligence operates on normalized semantic evidence.

---

# Provenance Is Still Preserved

Spatial agnosticism does **not** mean removing source coordinates.

Bounding boxes and page numbers remain valuable provenance.

The distinction is:

```text
Use geometry as provenance/evidence
```

rather than:

```text
Use geometry as the core risk data model
```

Therefore, coordinates may remain attached to source evidence while the generated risk itself operates on semantic relationships.

---

# Current Phase 2 Architecture

```text
Canonical Document JSON
          │
          ▼
   STEP 1 — Analysis
          │
          ├── Detect Risk Topics
          ├── Detect ESRS Topics
          ├── Identify Material Tables
          └── Associate Related Evidence
          │
          ▼
   risk_analysis.json
          │
          ▼
   STEP 2 — Generation
          │
          ├── Resolve Categories
          ├── Build Risk Contexts
          ├── Call Versioned Prompt
          ├── Parse Structured Output
          └── Validate with Pydantic
          │
          ▼
    Generated Risks
          │
          ├── page
          ├── section
          └── source_block_ids
          │
          ▼
       Risk Database
```

---

# Separation of Responsibilities

The system is intentionally divided into layers.

| Layer               | Responsibility                                           |
| ------------------- | -------------------------------------------------------- |
| Phase 1 Parser      | Extract information from the PDF                         |
| Normalization       | Convert parser-specific structures into canonical blocks |
| Analysis            | Locate risk-relevant evidence                            |
| Context Builder     | Assemble bounded semantic evidence                       |
| LLM                 | Interpret evidence and generate structured risks         |
| Schema Validation   | Enforce application contracts                            |
| Category Resolution | Normalize risk taxonomy                                  |
| Risk Database       | Persist derived risk intelligence                        |

This separation makes each component independently testable and replaceable.

---

# Important Engineering Principle

The architecture follows:

```text
Deterministic where possible
        +
LLM where semantic reasoning is required
```

Examples:

```text
SHA-256 identity             → Deterministic
Bounding-box association     → Deterministic
Schema validation            → Deterministic
Category normalization       → Controlled logic

Risk interpretation          → LLM
Risk description generation  → LLM
Semantic reasoning           → LLM
```

The LLM is therefore a reasoning component inside the system rather than the complete system itself.

---

# Runtime Failure — LLM Provider Rate Limit

Another failure observed during Phase 2 was:

```text
HTTP 429 Too Many Requests
```

while using an OpenRouter-hosted free model.

The provider returned a retry interval.

This failure is different from a schema-validation failure.

```text
Schema Failure
→ Model responded, application rejected the structure

Rate-Limit Failure
→ Provider did not allow the request to complete
```

This distinction is important for future retry and error-handling logic.

Provider failures should eventually support:

```text
Retry-After handling
Exponential backoff
Request throttling
Failure logging
Context-level retry
```

without restarting successfully completed work.

---

# Intermediate Persistence

Phase 2 intentionally stores intermediate analysis rather than treating the entire pipeline as one atomic operation.

```text
Canonical Document
      │
      ▼
Analysis
      │
      ▼
Persist Analysis
      │
      ▼
Generation
```

This provides:

* easier debugging,
* reproducibility,
* restartability,
* inspection of detected topics,
* isolation between deterministic and generative failures.

This becomes particularly important when LLM calls fail because of external provider issues.

---

# Current Status

At the current stage, Phase 2 can:

* Load the Phase 1 canonical document.
* Detect enterprise-risk and ESRS-related topics.
* Identify material tables.
* Associate nearby tables using page/block geometry.
* Persist intermediate risk analysis.
* Resolve risk categories.
* Build bounded risk contexts.
* Send individual contexts to a versioned risk-generation prompt.
* Parse structured LLM output.
* Validate generated output using Pydantic.
* Preserve source page, section, and block IDs.
* Generate structured enterprise risks.
* Distinguish application/schema failures from external provider failures.

---

# Current Experimental Result

During the current tested execution:

```text
Topics detected:          7
Material tables detected: 8
Topics without tables:    0
Risk contexts generated:  8
```

Generated examples included:

```text
Geopolitics and regulatory framework
Project execution
Cyber attacks
```

These results demonstrate that the Phase 1 canonical representation contains sufficient information to begin structured risk generation.

However, this does **not yet establish complete Phase 2 extraction accuracy**.

A dedicated risk-level evaluation methodology is still required.

---

# What Has Been Proven So Far?

### Proven

The Phase 1 output can successfully serve as input to a separate risk-intelligence layer.

Relevant risk evidence can be reduced into bounded contexts instead of sending the complete annual report to an LLM.

Spatial information can reconstruct relationships between independently extracted blocks.

Structured LLM output can be validated against application schemas.

Generated risks can preserve links to their source evidence.

### Not Yet Proven

The system has not yet demonstrated:

* complete principal-risk recall,
* risk-generation precision,
* category accuracy,
* duplicate-risk handling across contexts,
* cross-year risk matching,
* emerging-risk detection accuracy,
* production-scale reliability,
* provider-independent LLM performance.

These require separate evaluation.

---

# Long-Term Vision

Phase 2 should eventually transform document-level information into a reusable enterprise-risk knowledge layer.

The evolution is:

```text
Phase 1
Document Understanding
        │
        ▼
Phase 2
Risk Intelligence Extraction
        │
        ▼
Future Phase
Cross-Document Intelligence
```

The Risk Database should eventually allow the system to answer questions such as:

```text
What are Vestas's principal risks?

Which risks appeared for the first time this year?

Which risks disappeared?

Which risks increased in severity?

How has Cyber Risk changed over three years?

Which companies share similar supply-chain risks?

Which new risk themes are emerging across the industry?
```

This means the final system is not intended to be merely:

```text
PDF → LLM → Risk List
```

The intended architecture is:

```text
Documents
    │
    ▼
Canonical Evidence Layer
    │
    ▼
Risk Intelligence Extraction
    │
    ▼
Structured Risk Knowledge Base
    │
    ▼
Temporal / Comparative Intelligence
    │
    ▼
Search + Analytics + Emerging Risk Detection
```

---

# Key Design Decisions to Remember

| Decision                                                  | Why                                                           |
| --------------------------------------------------------- | ------------------------------------------------------------- |
| Phase 2 consumes Canonical JSON instead of Docling output | Keeps risk intelligence parser-independent                    |
| Analyze before generating                                 | Prevents sending the complete annual report to the LLM        |
| Persist `risk_analysis.json`                              | Enables debugging and restartability                          |
| Use geometry for nearby table association                 | Reconstructs obvious document relationships deterministically |
| Build bounded contexts                                    | Reduces irrelevant tokens and improves traceability           |
| Use LLM only for semantic reasoning                       | Keeps deterministic problems outside the generative layer     |
| Version prompts                                           | Makes generated results reproducible                          |
| Validate with Pydantic                                    | Prevents malformed LLM output entering the application        |
| Normalize categories                                      | Prevents uncontrolled taxonomy growth                         |
| Preserve `page`, `section`, `source_block_ids`            | Maintains evidence traceability                               |
| Separate Risk Database from Canonical Document            | Separates source evidence from derived intelligence           |
| Keep downstream architecture spatial agnostic             | Allows future non-PDF sources                                 |
| Persist intermediate state                                | Allows recovery from provider and generation failures         |

---

# Phase 2 Research Philosophy

The central idea of Phase 2 is:

> **Do not ask the LLM to understand everything that deterministic document structure already tells us.**

Instead:

```text
Structure determines WHERE to look.
        ↓
Context construction determines WHAT evidence to provide.
        ↓
LLM reasoning determines WHAT the evidence means.
        ↓
Schema validation determines WHETHER the result is acceptable.
        ↓
Provenance determines WHERE the answer came from.
```

This separation forms the foundation for the later Risk Intelligence System.
