# Docling Extraction Accuracy Evaluation — Vestas Annual Report 2025

**Method:** Rendered the 10 benchmark pages directly from the source PDF (150 dpi) and compared them line-by-line and number-by-number against the corresponding `.md`/`.json` Docling outputs. Financial tables were checked cell-by-cell; charts were checked by cropping/zooming to confirm color→legend→value mapping.

## Summary scorecard

| # | Page | Type | Difficulty | Text/Number Accuracy | Reading Order | Verdict |
|---|------|------|------------|:---:|:---:|---|
| 1 | 3 | Image + narrative | Easy | 100% | Correct | **Pass** — full letter text, heading, image tag all correct |
| 2 | 10 | 3-column text+image+quote | Easy–Medium | ~99% | Correct | **Pass** — all 3 columns read in correct order, quote + attribution captured |
| 3 | 8 | Dense bordered financial tables | Medium | 100% (all cells checked) | Correct | **Pass** — every one of ~35 line items across 5 years matches exactly |
| 4 | 9 | Multiple dense tables (Sustainability) | Medium–High | 100% (all cells checked) | Correct | **Pass** — Environmental/Social/Governance tables, all ~35 rows × 5 years match exactly |
| 5 | 7 | Charts + text + KPI cards | High | ~95% | Correct | **Pass with caveats** — bar/stacked-bar values correctly decoded via color, but chart legend labels not propagated to table headers (see below) |
| 6 | 13 | Circular diagram + text | High | Text: 100%; Diagram: 0% | Correct | **Partial** — all narrative + 3-column bullet lists captured perfectly; the infographic's own labels reduced to a generic image tag (no real loss since labels are duplicated in the text below) |
| 7 | 38 | World map infographic | Very High | ~5% | N/A | **Fail** — page has zero extractable text; all 3 regional KPI blocks (9 numbers) and ~20 country/facility markers lost |
| 8 | 50 | Circular ERM diagram + governance text | High | Text: 100%; Diagram: ~15% | Text correct; diagram merged out of order | **Partial** — governance columns (Audit/Assurance/Operational) fully accurate; only 1 of 5 wheel labels captured, and it was spliced mid-sentence into unrelated body text |
| 9 | 68 | End-to-end value-chain diagram | Very High | Text: 100%; Diagram: ~20% | Text correct; diagram fragments misplaced | **Partial** — all narrative paragraphs accurate; only 3 of ~14 value-chain stage labels captured (Customers/Asset managers, Decommissioning, Waste and end of life); 11 labels (Raw materials, Refiners and smelters, Transport, Manufacturing, Project development, etc.) and the Upstream/Own-operations/Downstream legend lost |
| 10 | 71 | Risk/IRO matrix table | Very High | 100% | Correct | **Pass** — every IRO description, value-chain tag, and materiality label across the 4-column matrix matches exactly |

**Overall: 6/10 pages fully accurate, 3/10 partially accurate (narrative text perfect, diagram-embedded labels largely lost), 1/10 failed outright.**

---

## Detailed findings

### Where Docling excels
- **Dense financial/ESG tables (pages 8, 9, 71):** This is the standout result. Every checked figure — ~100+ data points across income statement, balance sheet, cash flow, financial ratios, operational KPIs, environmental/social/governance metrics, and the IRO matrix — matched the source exactly, including parenthesized negatives (e.g., `(3,127)`, `(1,512)`), blank cells rendered as `-`, and multi-line/merged cells in the risk matrix.
- **Plain narrative + multi-column reading order (pages 3, 10, 13):** Column order is preserved correctly even in 3-column layouts, and body text is reproduced faithfully with no paraphrasing artifacts, dropped sentences, or merged paragraphs.
- **Bar chart value decoding (page 7):** This is genuinely impressive — Docling correctly parsed color-coded stacked/grouped bar charts (blue = Power Solutions, orange = Service, etc.) into a structured table, correctly signed the negative years (2022: −1,512), and matched the dotted-line EBIT-margin percentages. Verified by zooming into the source image.

### Where Docling struggles
1. **Semantic labeling of chart legends → table headers.** On page 7's "Order backlog value" chart, the output table uses generic column headers `Orange` / `Blue` instead of `Power Solutions` / `Service` (the actual legend text). The *values* are correct, but a downstream consumer can't tell what the columns mean without cross-referencing the image.
2. **Footnote superscripts merging into cell values.** Values like `0.13³` and `27.8⁴` were extracted as `0.1 3` and `27.8 4` (space-separated), which reads ambiguously — could be misread as two separate numbers rather than a value + footnote marker.
3. **Complex infographics/diagrams (pages 13, 50, 68, 38) — the core weakness.** Docling handles the *surrounding narrative text* around these diagrams perfectly, but the diagram's own embedded labels are the failure mode, with severity scaling directly with diagram complexity:
   - Page 13 (figure-8 loop): 0% of diagram labels captured, but no real harm — same labels are duplicated in the text below.
   - Page 50 (ERM wheel): only 1 of 5 quadrant labels captured, and it was spliced into an unrelated sentence, corrupting reading order at that point.
   - Page 68 (value-chain flow, "Very High" difficulty): only 3 of ~14 stage labels captured; the core content of the diagram (the actual value-chain steps: Raw materials → Refiners and smelters → Components and assembly → Transport → Operations & maintenance → Construction → Manufacturing → Project development, etc.) is almost entirely missing.
   - Page 38 (world map infographic, flagged for OCR): near-total failure. All three regional KPI blocks (Americas: 4,936 MW / 9,768 MW / 65 GW; EMEA: 9,841 MW / 17,796 MW / 79 GW; Asia Pacific: 1,515 MW / 3,462 MW / 16 GW) and ~20 country/facility markers were lost — the output is just an image tag. This matches the pipeline's own flag (`pages_with_text: 0`, `parser_status: completed_with_warnings`) confirming the OCR pass ran but extracted no usable text.

### Pattern
Docling's failure mode is consistent and predictable: **it is highly reliable for tables and running text (even multi-column), and increasingly unreliable as content complexity shifts from tabular/linear into freeform, spatially-scattered labels inside vector graphics** (charts with numeric bar labels are the exception — those are handled well because the numbers sit on a clear axis). Circular/flow diagrams and map infographics — where meaning depends on spatial position and connecting lines rather than reading order — are where information is lost.

---

## Recommendation
Given this pattern, before investing in broader pipeline optimization, it would be worth testing whether:
- A dedicated OCR/vision pass (rather than Docling's default layout parser) improves diagram/map-infographic pages specifically (pages like 38, 68, 50).
- Chart legend text can be explicitly linked to color-coded series so table headers use semantic names instead of `Orange`/`Blue`.
- Footnote markers can be split from adjacent numeric values via a post-processing regex (e.g., a digit immediately following a decimal number with a space is almost always a footnote reference, not part of the value).

Tables and plain/multi-column narrative text are already production-ready; diagram-heavy pages need either a different extraction strategy or manual/LLM-assisted post-processing before they can be trusted.