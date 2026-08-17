from __future__ import annotations

import argparse
import json

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluator import DocumentEvaluator


def load_json(
    path: Path,
) -> dict[str, Any]:

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def is_raw_docling_schema(
    canonical: dict[str, Any],
) -> bool:
    """
    Detect the raw docling-adaptive-pdf-parser output shape
    (page["content"] with docling block types such as
    "section_header") as opposed to the already-canonical shape
    the evaluator expects (page["blocks"] with block type
    "heading" and tables nested under block["table"]).
    """

    pages = canonical.get("pages", [])

    if not pages:
        return False

    sample_page = pages[0]

    return (
        "content" in sample_page
        and "blocks" not in sample_page
    )


def normalize_docling_block(
    block: dict[str, Any],
) -> dict[str, Any]:

    block_type = block.get("type")

    # docling labels section headings as "section_header";
    # the evaluator/golden set expects "heading".
    normalized_type = (
        "heading"
        if block_type == "section_header"
        else block_type
    )

    normalized: dict[str, Any] = {
        "type": normalized_type,
        "text": block.get("text", ""),
        "provenance": block.get("provenance"),
    }

    if block_type == "table":

        columns = block.get("columns", [])
        rows = block.get("rows", [])

        normalized["table"] = {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "column_count": len(columns),
        }

    return normalized


def normalize_docling_document(
    canonical: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert raw docling-adaptive-pdf-parser output into the
    canonical {"pages": [{"page_number", "blocks": [...]}]}
    shape that DocumentEvaluator expects.
    """

    normalized_pages = []

    for page in canonical.get("pages", []):

        normalized_pages.append(
            {
                "page_number": page.get(
                    "page_number"
                ),
                "blocks": [
                    normalize_docling_block(block)
                    for block in page.get(
                        "content",
                        [],
                    )
                ],
            }
        )

    return {"pages": normalized_pages}


def save_json(
    data: dict[str, Any],
    path: Path,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Evaluate canonical Phase 1 "
            "document output against golden set."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help=(
            "Canonical normalized JSON"
        ),
    )

    parser.add_argument(
        "--golden-dir",
        required=True,
        help=(
            "Golden-set directory"
        ),
    )

    parser.add_argument(
        "--output",
        default=None,
    )

    args = parser.parse_args()

    input_path = Path(
        args.input
    ).resolve()

    golden_dir = Path(
        args.golden_dir
    ).resolve()

    canonical = load_json(
        input_path
    )

    if is_raw_docling_schema(canonical):
        canonical = normalize_docling_document(
            canonical
        )

    pages = {
        page["page_number"]: page
        for page in canonical.get(
            "pages",
            [],
        )
    }

    evaluator = (
        DocumentEvaluator()
    )

    page_results = []

    for golden_file in sorted(
        golden_dir.glob(
            "page_*.json"
        )
    ):

        golden = load_json(
            golden_file
        )

        page_number = golden[
            "page_number"
        ]

        actual_page = pages.get(
            page_number
        )

        if actual_page is None:

            page_results.append(
                {
                    "page_number": (
                        page_number
                    ),
                    "status": (
                        "missing_page"
                    ),
                    "overall_score": 0.0,
                }
            )

            continue

        result = (
            evaluator.evaluate_page(
                actual_page=actual_page,
                golden=golden,
            )
        )

        page_results.append(
            result
        )

    page_scores = [
        result.get(
            "metrics",
            {},
        ).get(
            "overall_score",
            0.0,
        )
        for result in page_results
    ]

    overall_score = (
        sum(page_scores)
        / len(page_scores)
        if page_scores
        else 0.0
    )

    report = {
        "evaluation": {
            "dataset": (
                "Vestas Annual Report 2025"
            ),
            "evaluated_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
            "canonical_input": str(
                input_path
            ),
            "golden_directory": str(
                golden_dir
            ),
        },

        "summary": {
            "pages_evaluated": (
                len(page_results)
            ),
            "overall_score": (
                round(
                    overall_score,
                    4,
                )
            ),
        },

        "pages": page_results,
    }

    if args.output:

        output_path = Path(
            args.output
        )

    else:

        output_path = (
            Path(__file__)
            .resolve()
            .parent
            / "reports"
            / "evaluation_report.json"
        )

    save_json(
        report,
        output_path,
    )

    print(
        f"Evaluation report saved: "
        f"{output_path.resolve()}"
    )

    print(
        f"Overall score: "
        f"{overall_score:.4f}"
    )


if __name__ == "__main__":
    main()


#uv run run_evaluation.py --input "D:\Coding\Vestas\Pipeline\Risk-Intelligence-System\phase1\output\raw\VestasAnnualReport2025_09aa4e8bd783.json" --golden-dir "D:\Coding\Vestas\Pipeline\Risk-Intelligence-System\phase1\evaluation\text_extraction\golden"