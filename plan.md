# PLAN.md

## Product Context

The broader product is a **Risk Intelligence System** that helps analysts understand and compare principal risks disclosed in corporate annual reports.

The primary user is a **risk/research analyst** who currently has to manually read long reports, identify relevant risk disclosures, and trace them back to supporting evidence.

The eventual product surface would likely be an **interactive analyst UI backed by a batch/API processing pipeline**. Reports would be ingested in the background, converted into structured risk records, and surfaced through search, filtering, company/year comparison, and evidence links. In a later stage, the system could also alert analysts when new or materially changed risks appear.

For this assignment, I am implementing only the first useful slice:

```text
Annual Report PDF
        ↓
Structured Principal Risks
        ↓
Supporting Source Evidence
```

## Optimization Target

For this first slice, I am optimizing primarily for **correctness and traceability**, rather than maximum coverage, minimum cost, or throughput.

A smaller set of well-supported risks is more useful than a larger set containing hallucinated or weakly supported risks. Every generated risk should therefore remain traceable to the original report page/evidence.

This choice influences the implementation: deterministic parsing and evidence selection are preferred where possible, while the LLM is used mainly for semantic risk interpretation.

## Assumptions

* Input is an English corporate annual report in PDF format.
* Most principal-risk information is available through textual or tabular disclosures.
* A single report is processed at a time in this proof of concept.
* LLM output is probabilistic and must be validated before being accepted.
* Complex visual-only content such as maps, diagrams, and infographics may not be fully recoverable in the initial implementation.
* The analyst remains able to inspect the source evidence behind generated risks.

## Explicitly Deferred

This slice does not attempt to solve:

* multi-year risk matching and year-over-year change detection,
* cross-company risk comparison,
* emerging-risk alerts,
* semantic/vector search,
* automatic severity/probability scoring,
* complete chart/diagram understanding,
* production-scale distributed processing.

If given additional time, I would first extend the system to **multiple annual reports across years**, allowing risks to be matched and classified as new, persistent, changed, or disappeared.
