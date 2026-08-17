# Phase 1 – PDF Document Ingestion and Text Extraction

## Overview

The objective of Phase 1 is to build a reliable PDF ingestion pipeline capable of extracting page-level textual content from corporate annual reports while maintaining traceability, quality assessment, and structured outputs.

This phase intentionally focuses only on reliable document ingestion and basic text extraction. Advanced document understanding capabilities will be introduced incrementally in later phases.

---

## Research Boundary

The first stage investigates only the following research question:

> **Can the system reliably open, inspect, and extract page-level textual content from PDF documents while preserving traceability and reporting extraction quality?**

**Minimum ingestion acceptance criteria:**
  - Preserved correct page numbers.
  - Page text should not be empty or severely corrupted.
  - Headings & body text should be in usable reading order.
  - Extracted text can be track from original PDF page.
  - Record the Parser failure clearly.

The following capabilities are **explicitly outside the scope** of this phase:

- Perfect reading-order reconstruction
- Advanced table reconstruction
- Chart understanding
- Image caption generation
- Section-aware chunking
- Risk extraction
- Risk scoring
- Semantic search
- Embedding generation
- Vector database storage

These capabilities will be introduced after the document ingestion pipeline becomes sufficiently reliable.

---

## Goal 1 — PDF Intake and Basic Text Extraction

### Input

- Corporate Annual Report (PDF)

---

### Processing Pipeline

```
PDF Intake
      │
      ▼
File Validation
      │
      ▼
Document Identity Generation
      │
      ▼
Duplicate Check
      │
      ▼
PDF Metadata Inspection
      │
      ▼
Page Enumeration
      │
      ▼
Page-level Text Extraction
      │
      ▼
Basic Text Normalisation
      │
      ▼
Extraction Quality Checks
      │
      ▼
Structured Document Output
      │
      ▼
Error & Warning Report
```

---

### Outputs

The ingestion pipeline produces:

- Structured document JSON
- Extraction quality report
- Processing logs
- Raw parser output
- Document-level metadata
- Page-level metadata

---

### Minimum Structured Output

```json
{
  "document_id": "generated-unique-id",
  "document_hash": "sha256-value",
  "source": {
    "file_name": "VestasAnnualReport2025.pdf",
    "file_type": "pdf",
    "file_size_bytes": 0
  },
  "document_metadata": {
    "page_count": 195,
    "title": "Annual Report 2025",
    "author": null,
    "creation_date": null,
    "is_encrypted": false
  },
  "processing": {
    "parser_name": "parser-identifier",
    "parser_version": "version",
    "processing_started_at": "timestamp",
    "processing_completed_at": "timestamp",
    "status": "completed_with_warnings"
  },
  "pages": [
    {
      "page_number": 1,
      "raw_text": "Original parser output",
      "clean_text": "Normalised page text",
      "character_count": 120,
      "word_count": 18,
      "extraction_status": "success",
      "warnings": [],
      "metadata": {}
    }
  ],
  "quality": {
    "pages_processed": 195,
    "pages_with_text": 180,
    "empty_pages": 15,
    "failed_pages": 0,
    "overall_quality_score": 0.91
  },
  "errors": []
}
```

---

### Parser Architecture

The ingestion framework is designed around an **Abstract Base Class (ABC)** that defines a common contract for every document parser.

The base class does not perform parsing itself. Instead, it ensures that every parser implements a consistent interface before entering production.

Every parser must implement the following methods.

---

#### `can_parse()`

Determines whether the parser supports the supplied document.

Example:

```python
parser.can_parse(file_path)
```

Returns:

```python
True
```

or

```python
False
```

---

#### `inspect()`

Performs lightweight document inspection without fully parsing the PDF.

Example output:

```json
{
  "pages": 220,
  "encrypted": false,
  "has_images": true,
  "file_size_mb": 25.4,
  "language": "English"
}
```

---

#### `parse()`

Performs the complete parsing process.

Example output:

```json
{
  "metadata": {
    ...
  },
  "pages": [
    {
      "page": 1,
      "blocks": [
        ...
      ]
    }
  ]
}
```

---

### Document Identity and Duplicate Detection

Each document is uniquely identified using a **SHA-256** content hash.

The hash is computed before parsing begins.

The processing workflow is:

```
PDF
   │
   ▼
Calculate SHA-256
   │
   ▼
Lookup Processing Registry
   │
   ├──────── Exists & Completed ───────► Skip Processing
   │
   ▼
Parse Document
```

---

#### Why SHA-256?

SHA-256 was selected because:

- It uniquely identifies document content.
- Collision probability is extremely low.
- It is widely supported.
- It is suitable for production-scale document identification.

Unlike filenames, the hash depends only on file content.

Therefore,

- Same content + different filename → identical hash
- Same filename + different content → different hash

---

### Processing Registry

For this Proof of Concept (PoC), the processing registry is implemented using a JSON file.

Advantages:

- Simple
- Lightweight
- Human-readable
- No database setup required

However, JSON is suitable only for:

- Small datasets
- Sequential processing
- Single-user execution

Limitations include:

- Poor concurrency support
- Slower lookup as data grows
- Risk of corruption during simultaneous writes

Future implementations may replace the JSON registry with:

- SQLite
- PostgreSQL
- Redis
- DynamoDB

These alternatives provide:

- Atomic updates
- Concurrent access
- Faster lookups
- Better scalability
- Improved fault tolerance

---

### Layout Analysis and Content Extraction

Corporate reports contain heterogeneous content including:

- Narrative text
- Financial tables
- Charts
- Images
- Maps
- Infographics
- Process diagrams

No single parser handles every content type accurately.

Initial experiments were conducted using independent extraction libraries.

| Library | Primary Limitation |
|----------|-------------------|
| PyMuPDF | Borderless and highly complex tables |
| pdfplumber | Limited understanding of charts and diagrams |

---

#### Solution A — Hybrid Extraction Pipeline

Different content regions are processed using specialised tools.

```
               PDF Page
                   │
                   ▼
          Layout Detection
                   │
     ┌─────────────┼─────────────┐
     ▼             ▼             ▼
 Text Region   Table Region  Figure Region
     │             │             │
     ▼             ▼             ▼
 PyMuPDF      pdfplumber      Image Crop
     │             │             │
     ▼             ▼             ▼
 Text JSON     Table JSON   Vision Model
                   │             │
                   └──────┬──────┘
                          ▼
                  Standard Schema
```

---

#### Solution B — Docling-Based Pipeline

Docling performs layout detection first, followed by content-specific extraction.

```
PDF
 │
 ▼
Pass 1: Layout Analysis (OCR Disabled)
 │
 ├── Text Region
 ├── Table Region
 ├── Picture Region
 ├── Chart Region
 ├── Diagram Region
 └── Scanned Page
           │
           ▼
Pass 2: Content-specific Extraction
 │
 ├── Text      → Native text extraction
 ├── Table     → Markdown table
 ├── Chart     → Chart extraction
 ├── Diagram   → Picture classification
 └── Scanned   → OCR (only when required)
           │
           ▼
Merge into Standard JSON
```

---

### Challenges Identified

The following challenges were observed during experimentation.

#### Complex PDF Structures

Annual reports combine multiple content types within a single page, making extraction difficult.

---

#### Multi-column Reading Order

Many extraction libraries incorrectly interleave columns, producing unreadable text.

---

#### Table Extraction

Borderless and dense tables frequently lose their row-column relationships.

---

#### Charts and Diagrams

Visual semantics cannot be recovered through text extraction alone.

---

#### OCR Usage

OCR is necessary only for scanned pages.

Running OCR on every page:

- increases processing time,
- increases memory usage,
- sometimes produces empty or noisy output.

---

#### Hybrid Processing Complexity

Different content types require different extraction tools, increasing pipeline complexity.

---

#### Resource Consumption

Processing the entire 195-page report requires substantial memory and compute resources.

This slows debugging and experimentation.

---

### Evaluation Coverage

A representative benchmark is required to accurately evaluate parser performance across diverse layouts.

---

#### Experimental Design

Two independent research questions were identified.

1. Can the parser accurately understand different page layouts?
2. Can the entire report be processed within available computational resources?

These questions should be evaluated separately.

Resource optimisation is considered a future engineering task.

The current work focuses exclusively on validating extraction quality.

---

#### Benchmark Dataset

Ten representative pages were selected from the annual report.

These pages cover a broad range of layouts and content complexity.

| PDF Page | Difficulty | Page Type | Validation Criteria |
|-----------|------------|-----------|---------------------|
| **3** | Easy | Image + narrative text | Heading order, paragraph order, image separation, header/footer |
| **10** | Easy–Medium | Three-column text + image + quote | Multi-column reading order |
| **8** | Medium | Dense bordered financial table | Rows, columns, headers, negative values, footnotes |
| **9** | Medium–High | Multiple dense tables | Separate tables, shared headers, multiline cells |
| **7** | High | Charts + text + KPI cards | Chart detection versus text |
| **13** | High | Circular diagram + narrative | Diagram detection, scattered labels |
| **38** | High | World map infographic | Figure detection and spatial labels |
| **50** | High | ERM circular diagram | Diagram and governance hierarchy |
| **68** | Very High | Value-chain diagram | Flow diagram and connected labels |
| **71** | Very High | Risk/IRO matrix | Complex semantic table |

---

#### Experimental Results

| Result | Pages | Count |
|----------|-------|------:|
| Full Pass | 3, 8, 9, 10, 13, 71 | 6 |
| Partial Pass | 7, 50, 68 | 3 |
| Failed | 38 | 1 |

---

### Docling Evaluation Summary

#### Overall Performance

- Full Success: **6 / 10 pages**
- Partial Success: **3 / 10 pages**
- Failure: **1 / 10 pages**

---

#### Strengths

Docling performs reliably for:

- Narrative text
- Multi-column layouts
- Financial tables
- Sustainability tables

Table extraction accuracy was close to 100%.

Bar charts were generally extracted correctly, with only minor issues involving legends and footnotes.

---

#### Limitations

Docling struggles with:

- Process diagrams
- Flowcharts
- Circular governance diagrams
- Value-chain illustrations
- Infographics
- Maps

Although surrounding text is extracted correctly, embedded labels within graphics are frequently lost.

---

#### Major Failure

The world map infographic (Page 38) was extracted only as an image.

Consequently,

- embedded labels,
- country names,
- numerical values,
- spatial information

were completely lost.

---

#### Conclusion

The experimental hypothesis is **accepted** for the intended scope of this assignment.

Docling provides sufficiently accurate extraction for:

- narrative text,
- multi-column layouts,
- financial tables,
- sustainability tables,
- textual risk disclosures.

Visual semantic understanding is intentionally deferred because it is outside the scope of Phase 1.

---

#### Key Takeaways

| Claim | Status | Justification |
|--------|--------|---------------|
| Docling is fully production-ready | ❌ No | Diagram, map, and infographic understanding remains incomplete. Large-scale production validation has not yet been performed. |
| Parser handles every PDF content type | ❌ No | Performance is strong for text and tables but limited for visual-only content. |
| Parser is suitable for textual and tabular risk disclosures | ✅ Yes | Representative-page testing demonstrated reliable extraction of narrative text and complex tables. |
| Parser satisfies the current assignment scope | ✅ Yes | Phase 1 focuses exclusively on textual and tabular risk disclosures. |
| Visual semantic parsing is deferred | ✅ Yes | Maps, diagrams, charts, and infographics will be addressed in future work. |
| Full-report optimisation remains future work | ✅ Yes | Current validation focuses on extraction quality. Memory optimisation, batching, and streaming will be implemented in subsequent phases. |

## Goal 2 — Normalization and Centralization

### Why normalization was required?

The raw Docling output had three important limitations.

1. Parser-specific representation
  Docling uses its own labels and object structure, such as:
  - section_header
  - picture
  - flow_chart
  If downstream components directly depend on these labels, replacing Docling later would require changes across the entire system.

2. Extraction artifacts
  Some extracted content contained noise such as:
  - control characters
  - inconsistent whitespace
  - decorative icons
  - non-essential visual elements

3. Lost semantic relationships
  Certain structures were extracted correctly as individual objects but their relationships were lost.
  Page 51 was the main example:
```
Risk headings
     +
Table content
```
  were both available, but were not linked together.

### Normalization approach

A normalization layer was introduced between the parser and downstream processing.
```
PDF
 │
 ▼
Docling Parser
 │
 ▼
Raw Parser JSON
 │
 ▼
Normalization Layer
 │
 ├── Type mapping
 ├── Text cleanup
 ├── Decorative visual filtering
 ├── Table reconstruction
 └── Provenance preservation
 │
 ▼
Canonical Document JSON
```

The normalization layer converts parser-specific output into our own canonical schema.

For example:

```
Docling: section_header
        ↓
Canonical: heading
```

This keeps downstream components independent of the parsing library.

### Table reconstruction decision

For cases such as page 51, bounding-box geometry is used to associate headings located directly above the table with the corresponding table columns.

The normalized table becomes:
- attribute
- Geopolitics and regulatory framework
- Project execution
- Cyber attacks

instead of:
```
0
1
2
3
```
This reconstruction is deterministic and does not require an LLM.

### Canonical representation

The normalized output is built around a parser-independent document structure:
```
Document
 │
 ├── metadata
 ├── pages
 │    └── blocks
 │         ├── text
 │         ├── heading
 │         ├── table
 │         ├── image
 │         ├── chart
 │         └── diagram
 │
 └── provenance
```
Page numbers and bounding boxes are preserved because later stages must be able to trace extracted risks back to their source evidence.

### Document Centralization

During testing, partial page ranges were processed independently.

Initially this produced separate outputs such as:
- VestasAnnualReport2025_pages_50_51.json
- VestasAnnualReport2025_pages_71_74.json

This was undesirable because both files represent the same source document.

**Decision**

The persistence model was changed from run-centric to document-centric.

The document SHA-256 hash is now used as the stable document identity.

For the same PDF:
- One Raw JSON
- One Canonical JSON
- One Registry Record

regardless of how many partial runs are performed.

Example:
- Run 1:
```
pages 50–51

Stored pages:
[50, 51]
```
- Run 2:
```
pages 71–74

Stored pages:
[50, 51, 71, 72, 73, 74]
```

If a requested page already exists:
```
without --force
→ skip
```
```
If it is explicitly reprocessed:
with --force
→ replace existing page
```
```
If the page does not exist:
→ append
```
The final page collection is always sorted by page number.


## Current Architecture
```
Corporate Annual Report PDF
            │
            ▼
        SHA-256
            │
            ▼
   Docling Two-Pass Parser
            │
            ▼
      Raw Parser JSON
            │
            ▼
     Normalization Layer
            │
            ▼
   Canonical Document JSON
            │
            ▼
  Document-Level Persistence
            │
            ├── Existing page → Update
            └── New page      → Append
```

### Current Status

At this stage, Phase 1 can:

- Parse selected PDF pages using Docling
- Perform selective OCR
- Preserve text, tables, visuals, and provenance
- Normalize parser-specific output into a canonical format
- Reconstruct some lost table semantics using layout geometry
- Maintain one document representation across multiple partial runs
- Track processing state through a document-level registry

## Goal 3 — Evaluation

### What Was Done?

#### 1. Created a Golden Dataset (10 Pages)

A dedicated JSON file was created using claude sonnet 5 medium model for each evaluation page:

```text
golden_vestas_2025/
├── page_03.json
├── page_07.json
├── page_08.json
├── page_09.json
├── page_10.json
├── page_13.json
├── page_38.json
├── page_50.json
├── page_68.json
└── page_71.json
```

Each file contains:

* `expected_headings`
* `required_text_fragments`
* `expected_tables`

  * columns
  * row count
  * column count
  * required row labels
* `provenance_required`

To avoid circular evaluation, the golden dataset was **not** created solely from Docling output. 
Each page was independently verified using the original PDF (`pdftotext`) and page images to ensure the expected content accurately reflects the source document.

---

#### 2. Handled Known Docling Limitations

Some pages contain graphics that are outside the scope of reliable text extraction. These were intentionally handled as follows:

* **Page 38 (World Map):** Only the page title was expected; map labels were excluded.
* **Page 13 (Wind Energy Value Drivers Diagram):** Circular diagram labels were ignored, while duplicated textual headings below the figure were retained.
* **Page 50 (ERM Wheel):** Internal Q1–Q4 labels were excluded; governance-related text was preserved.
* **Page 68 (Value Chain Illustration):** Illustration captions (e.g., *Raw Materials*, *Transport*) were ignored; only the narrative content was evaluated.
* **Page 71 (Infographic):** Icons were excluded, while the table and surrounding narrative were included.

---

#### 3. Updated `run_evaluation.py`

The evaluator expected a canonical document format, while the raw Docling output used a different schema.

To bridge this difference, a `normalize_docling_document()` function was added to:

* Detect the raw Docling schema automatically.
* Convert parser-specific blocks into the evaluator's canonical structure.
* Map content into `page["blocks"]`.
* Convert `section_header` into `heading`.
* Normalize table structures into the expected format.

---

### Evaluation Results

**Overall Score: 0.975**

| Page                           |  Overall |  Heading | Text | Table | Provenance |
| ------------------------------ | :------: | :------: | :--: | :---: | :--------: |
| 3, 7, 8, 9, 10, 13, 50, 68, 71 | **1.00** |   1.00   | 1.00 |  1.00 |    1.00    |
| 38                             | **0.75** | **0.00** | 1.00 |  1.00 |    1.00    |

---

### Evaluation Metrics Breakdown

For each page, four metrics are calculated. The **overall page score** is the simple average of these four metrics.

---

#### 1. Heading Recall

**Formula**

```text
heading_recall = matched_headings / expected_headings
```

**How it works**

* `expected_headings` comes from the golden dataset.
* All blocks with `type == "heading"` are collected from the extracted document.
* Both expected and extracted headings are compared in a **case-insensitive** manner.
* The score is the proportion of expected headings that were successfully found.

**Edge Case**

If the golden dataset contains no expected headings (`expected_headings = []`), the score is automatically **1.0** because there are no headings to evaluate.

> This is why page 38 still includes one expected heading. If the list were empty, the heading score would always be **1.0**, even if the parser failed to extract any headings.

---

#### 2. Text Fragment Recall

**Formula**

```text
text_fragment_recall = matched_fragments / required_text_fragments
```

**How it works**

* All page content is combined into a single lowercase text string, including:

  * Normal text blocks
  * Table cells
  * Table column headers
* Each required text fragment from the golden dataset is searched using a simple substring match:

```python
fragment.lower() in actual_text
```

**Note**

During evaluation, page 3 exposed an issue caused by justified PDF text, where multiple spaces appeared (e.g., `"201  GW  of  installed"`). Since substring matching is exact, fragments with single spaces failed to match. To avoid false negatives, all text fragments were normalized and verified before being added to the golden dataset.

---

#### 3. Table Metrics

Table evaluation is performed at two levels.

**Page Level**

If a page contains multiple expected tables:

```text
page_table_score = average(table_1_score, table_2_score, ...)
```

Each expected table is matched with the table at the same index in the extracted output. If an expected table is missing, its score is **0.0**.

---

**Per-Table Evaluation**

Each table is evaluated using four independent checks.

| Check        | Pass Condition                                                                    |
| ------------ | --------------------------------------------------------------------------------- |
| Row Count    | Expected row count equals extracted row count (or expected value is `None`)       |
| Column Count | Expected column count equals extracted column count (or expected value is `None`) |
| Headers      | Expected and extracted column headers match (case-insensitive, same order)        |
| Row Labels   | Every required row label exists in the first column of the extracted table        |

**Formula**

```text
table_score = passed_checks / 4
```

For example, pages 8 and 9 use exact row and column counts (e.g., **24 × 6**, **20 × 6**). Even if the headers and row labels match perfectly, incorrect dimensions would cause two of the four checks to fail.

---

#### 4. Provenance Coverage

**Formula**

```text
provenance_coverage = blocks_with_provenance / total_blocks
```

**How it works**

* If `provenance_required` is **false** in the golden dataset, the score is automatically **1.0**.
* Otherwise, every block on the page (headings, text, tables, images, etc.) is checked.
* The score is the proportion of blocks that contain valid provenance information.

**Edge Case**

If a page contains zero blocks (such as page 38), the score is **0.0** to avoid division by zero.

---

#### 5. Overall Page Score

The final score for each page is an unweighted average of the four metrics.

```text
overall_score =
(
    heading_recall +
    text_fragment_recall +
    table_metrics +
    provenance_coverage
) / 4
```

Each metric contributes **25%** of the overall page score.

---

#### 6. Overall Document Score

The document-level score is also calculated as a simple average.

```text
overall_score =
sum(page_overall_scores) / number_of_pages
```

Every page contributes equally to the final score, regardless of whether it contains extensive text or only graphical content.

---

#### 7. Note on Page 38

Page 38 received an overall score of **0.75** because only the heading metric was meaningfully evaluated.

* **Heading Recall:** 0.0 (expected heading not extracted)
* **Text Fragment Recall:** 1.0 (no required text fragments)
* **Table Metrics:** 1.0 (no expected tables)
* **Provenance Coverage:** 1.0 (`provenance_required = false`)

Therefore:

```text
(0.0 + 1.0 + 1.0 + 1.0) / 4 = 0.75
```

This score reflects the current evaluation design, where all four metrics have equal weight, even if only one metric is applicable for a particular page.

---

### Performance Summary

The pipeline achieved **perfect scores (1.0)** on narrative text extraction, tables, and multi-column layouts across all evaluated pages except one. 
This confirms that Docling performs reliably for structured document content.
The only remaining gap is **Page 38 (World Map)**. Docling classified the page as **image/scanned content**, resulting in no extracted text or headings. Consequently, even the page title (*Our Global Footprint*) was not detected. This is a known limitation for map-based pages and represents the only evaluation failure. If downstream Risk Intelligence depends on text from such pages, an OCR or vision-based fallback would be required.
