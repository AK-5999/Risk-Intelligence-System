# Risk Intelligence System

---

# Introduction

Corporate risk intelligence requires analyzing hundreds of annual reports every quarter to understand how companies identify and communicate their key risks.

## Current Process

- Analysts manually review corporate annual reports.
- They identify principal risks, risk categories, and year-over-year changes.
- Insights are consolidated for asset managers and compliance teams.

## Challenges in the Current Process

- Time-consuming
- Expensive
- Limited scalability
- Inconsistent results

## Proposed Solution

Build an **AI-powered, structured, searchable Risk Intelligence Platform** that can:

- Extract principal risks automatically from reports.
- Categorize risks consistently.
- Track risk evolution year over year.
- Identify emerging risks across industries and portfolios.

```text
[Annual Reports]
       │
       ▼
[Hybrid Document Processing]
       │
       ▼
[Structured Information]
       │
       ▼
   [Database] ◄──── [User Query]
       │
       ▼
[Context Assembly] ──► [AI-based Reasoning] ──► [Answer with Citations]
```

## Detailed Process

### 1. Input: Annual Reports

Companies publish risk information in lengthy and unstructured annual reports. The first step is to ingest these documents.

### 2. Hybrid Document Processing

Using AI and standard document-processing techniques, the system extracts:

- Risk disclosures
- Company information
- Risk categories
- Contextual information

### 3. Structured Risk Database

The extracted information is transformed into structured data, enabling comparison across companies and reporting periods.

### 4. Query & Retrieval Layer

Analysts can ask business questions, and the system retrieves the most relevant risk information from the database.

### 5. AI Reasoning & Response Generation

The AI engine analyzes the retrieved information, identifies trends, and generates evidence-backed answers with citations from the original reports.

---

# Progress Plan

The development lifecycle is organized into five sequential phases.

Each phase follows the same internal execution pipeline:

> **Research → PoC → Evaluation → Scale → Test → Deploy**

```text
Annual Reports
       │
       ▼
Phase 1: Document Intelligence & Data Ingestion
       │
       ▼
Phase 2: Risk Extraction & Evaluation
       │
       ▼
Phase 3: Intelligent Retrieval & Search
       │
       ▼
Phase 4: AI Reasoning & User Experience
       │
       ▼
Phase 5: Evaluation, Monitoring & Optimization
       │
       ▼
Production-Ready Risk Intelligence Platform
```

---

# Phase 1: Document Intelligence & Data Ingestion

```text
PHASE 1
Document Intelligence & Data Ingestion

        │
        ├── Research
        │      ↓
        │   Experiments
        │      ↓
        │   Decision Matrix
        │
        ├── PoC
        │      ↓
        │   Minimal Vertical Slice
        │
        ├── Evaluation
        │      ↓
        │   Golden Set + Failure Cases
        │
        └── Production Design
               ↓
      Scalability Plan → Test → Deploy
      (not full implementation)
```

## Document Ingestion

Build the foundational layer that reliably transforms unstructured annual reports into structured, machine-readable information for AI-driven risk analysis.

This phase focuses on developing a measurable, traceable, and parser-independent document ingestion system capable of progressively handling increasingly complex corporate reports.

### What We Build

#### Input

- 📄 Corporate Annual Report (PDF)

#### Processing

- Programmatically ingest PDF documents.
- Extract textual content while maintaining page-level traceability.
- Convert raw document content into a structured representation.
- Validate extraction quality against the original report.
- Capture extraction errors and document complexities for continuous improvement.

#### Output

- ✅ Clean, structured, and traceable document data ready for downstream AI processing.

---

## Key Design Principle

### Parser-Agnostic Architecture

The ingestion layer remains independent of any specific extraction technology, enabling:

- Easy experimentation with multiple document extraction approaches.
- Replacement of parsing engines without impacting downstream systems.
- Continuous improvement as document complexity increases.

---

## Long-Term Vision

The architecture is designed to support multiple corporate document formats, including:

- PDF annual reports
- Microsoft Word documents
- Excel workbooks
- PowerPoint presentations
- Scanned reports
- Image-based documents

> **Initial Scope:** The research phase will focus exclusively on corporate annual reports in **PDF** format. Support for additional document types is planned as part of the platform's future extensibility.

---

## Architecture

```text
        PDF Annual Report
                │
                ▼
      Document Ingestion Layer
                │
     ┌──────────┴──────────┐
     ▼                     ▼
Text Extraction      Quality Validation
     │                     │
     └──────────┬──────────┘
                ▼
 Structured Document Data
(Text + Page Mapping + Metadata)
                │
                ▼
Next Layer: Risk Extraction & RAG Pipeline
```

---

## Data Types Present in Annual Reports

Annual reports contain multiple forms of information—including text, tables, visuals, and structured disclosures.

The ingestion layer must intelligently capture and preserve these data types to provide a reliable foundation for AI-driven risk intelligence.

| Data Type | Primary Usage | Example |
|-----------|---------------|---------|
| Text | Risk extraction & reasoning | Risk descriptions |
| Tables | Structured risk comparison | Risk matrices |
| Metadata | Search & citation | Report year, page number |
| Headings | Context preservation | Table of contents |
| Charts | Trend analysis | Revenue graphs |
| Diagrams | Framework understanding | Supply chain flow |
| Images | Additional context | Product images, logos |
| Images | Additional context | Product images, logos |



# Phase 2: Risk Extraction & Evaluation

```text
PHASE 2
Risk Extraction & Evaluation
├── Risk Analysis
│   ├── Parsed JSON Reader
│   ├── Table Identification
│   ├── Section / Topic Hierarchy
│   └── Candidate Context Preparation
│
├── Generation Experiments
│   ├── OpenRouter LLM
│   ├── Prompt Store
│   └── Versioned Risk Extraction
│
├── Schema Validation & Structuring
│   ├── Pydantic
│   ├── Grounding Checks
│   └── Final risks.json
│
├── Evaluation
│   ├── Golden Dataset
│   ├── Failure Cases
│   └── Regression Evaluator
│
└── Production Design
    Scalability Plan → Test → Deploy
    (not full implementation)
```
## Risk Database

The Risk Database is the structured storage layer of Phase 2. It stores the validated and analyzed risk information produced from annual reports in a consistent, traceable format.

Instead of storing only extracted text, the database captures the **risk as a structured entity** along with its supporting context and source information.

Typical information includes:

* Risk title and description
* Risk category and sustainability topic
* Impact, financial risk, or opportunity information
* Risk-management actions and mitigation measures
* Source document, page, section, and block references
* Reporting year and company information
* Evidence required to trace the extracted information back to the original report

The database therefore acts as the bridge between **document-level extraction** and later capabilities such as risk comparison, search, trend analysis, and AI-assisted reasoning.

---

## Key Design Principle

### Spatial Agnostic Architecture

The Risk Database is designed to be **spatially agnostic**.

Annual reports are highly layout-dependent. The same risk may appear in different pages, sections, tables, or positions across different companies and reporting years. The database should therefore not depend on a fixed document layout or assumptions such as:

* Risk information always appearing on a specific page
* Risk title and mitigation being located next to each other
* A fixed table structure
* The same section order across reports
* The same layout being maintained year over year

During parsing and analysis, spatial information such as **page number, block ID, section hierarchy, and table position** is preserved for traceability. However, these coordinates do not define the logical structure of the stored risk.

The architecture separates:

**Physical Document Structure**

`Page → Block → Table/Text → Section`

from:

**Logical Risk Structure**

`Company → Reporting Year → Risk → Category → Evidence → Management Response`

This allows the system to reconstruct a risk from multiple pieces of evidence while remaining independent of how the source document is visually organized.

---

## Long-Term Vision

The Risk Database is designed as a foundation for a broader **Risk Intelligence System**, rather than as storage for a single annual report.

As additional reports are processed, the database can evolve into a historical risk knowledge layer capable of supporting:

* **Year-over-Year Risk Tracking** — identify how an existing risk changes across reporting periods.
* **New and Emerging Risk Detection** — identify risks appearing for the first time.
* **Risk Evolution Analysis** — detect changes in risk description, severity, impact, or management strategy.
* **Cross-Company Comparison** — compare similar risks across organizations or industries.
* **Risk Search and Retrieval** — retrieve risks by company, year, category, topic, or supporting evidence.
* **Evidence-Based AI Reasoning** — provide structured and traceable context to downstream LLM or analytical components.
* **Auditability** — trace every generated insight back to the original report, page, section, and supporting evidence.

The long-term objective is to transform annual reports from isolated documents into a **queryable, historical, and traceable risk intelligence knowledge base**.

The architecture therefore follows a simple principle:

**Documents are the source, risks are the entities, evidence provides traceability, and time creates intelligence.**
