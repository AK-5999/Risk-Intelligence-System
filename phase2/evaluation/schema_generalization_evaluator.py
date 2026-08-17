from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any


# ----------------------------------------------------------------------
# PROJECT ROOT
# ----------------------------------------------------------------------

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


from src.risk_candidate_extractor import RiskCandidateExtractor


class NullLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


class SchemaGeneralizationEvaluator:
    """
    Verify that RiskCandidateExtractor is driven by the normalized
    semantic table schema rather than specific Vestas risk names.
    """

    def __init__(
        self,
        cases_path: Path,
    ):
        self.cases_path = cases_path

    @staticmethod
    def _load_json(
        path: Path,
    ) -> dict[str, Any]:

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    @staticmethod
    def _build_analysis_fixture(
        table: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Wrap one synthetic table in the same intermediate structure
        produced by RiskAnalyzer.
        """

        return {
            "document": {
                "document_id": "synthetic-generalization-test",
                "document_hash": "synthetic",
                "source": {
                    "file_name": "synthetic.json",
                    "file_type": "json"
                }
            },
            "risk_analysis": {
                "enterprise_risks": None,
                "material_impacts_risks_and_opportunities": {
                    "section": (
                        "Material impacts, risks, and opportunities"
                    ),
                    "topics": [
                        {
                            "topic_code": "E99",
                            "topic_name": "Synthetic Topic",
                            "pages": [999],
                            "tables": [
                                {
                                    "page": 999,
                                    "block_id": "synthetic-block-1",
                                    "columns": table[
                                        "columns"
                                    ],
                                    "rows": table[
                                        "rows"
                                    ],
                                    "row_count": len(
                                        table["rows"]
                                    ),
                                    "column_count": len(
                                        table["columns"]
                                    ),
                                    "normalized": True,
                                    "provenance": []
                                }
                            ]
                        }
                    ]
                }
            }
        }

    def _run_case(
        self,
        case: dict[str, Any],
    ) -> dict[str, Any]:

        fixture = (
            self._build_analysis_fixture(
                case["table"]
            )
        )

        with tempfile.TemporaryDirectory() as directory:

            input_path = (
                Path(directory)
                / "risk_analysis.json"
            )

            with input_path.open(
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    fixture,
                    file,
                    indent=2,
                    ensure_ascii=False,
                )

            extractor = (
                RiskCandidateExtractor(
                    input_path=input_path,
                    logger=NullLogger(),
                )
            )

            output = extractor.extract()

        analysis = output[
            "candidate_analysis"
        ]

        expected = case[
            "expected"
        ]

        actual_candidate_count = (
            analysis[
                "candidate_count"
            ]
        )

        actual_excluded_count = (
            analysis[
                "excluded_count"
            ]
        )

        checks = {
            "candidate_count_match": (
                actual_candidate_count
                == expected[
                    "candidate_count"
                ]
            ),
            "excluded_count_match": (
                actual_excluded_count
                == expected[
                    "excluded_count"
                ]
            ),
        }

        expected_text = expected.get(
            "expected_candidate_contains"
        )

        if expected_text:

            candidate_texts = [
                candidate.get(
                    "candidate_text",
                    "",
                )
                for candidate
                in analysis[
                    "candidates"
                ]
            ]

            checks[
                "candidate_content_match"
            ] = any(
                expected_text.lower()
                in text.lower()
                for text
                in candidate_texts
            )

        expected_reason = expected.get(
            "expected_exclusion_reason"
        )

        if expected_reason:

            reasons = [
                item.get(
                    "reason"
                )
                for item
                in analysis[
                    "excluded_items"
                ]
            ]

            checks[
                "exclusion_reason_match"
            ] = (
                expected_reason
                in reasons
            )

        passed = all(
            checks.values()
        )

        return {
            "case_id": case[
                "id"
            ],
            "description": case[
                "description"
            ],
            "passed": passed,
            "checks": checks,
            "actual_candidate_count": (
                actual_candidate_count
            ),
            "actual_excluded_count": (
                actual_excluded_count
            ),
        }

    def evaluate(
        self,
    ) -> dict[str, Any]:

        data = self._load_json(
            self.cases_path
        )

        case_results = [
            self._run_case(case)
            for case
            in data.get(
                "cases",
                [],
            )
        ]

        passed = sum(
            1
            for result in case_results
            if result[
                "passed"
            ]
        )

        total = len(
            case_results
        )

        return {
            "suite": (
                "schema_generalization"
            ),
            "total_cases": total,
            "passed_cases": passed,
            "failed_cases": (
                total - passed
            ),
            "pass_rate": (
                round(
                    passed / total,
                    4,
                )
                if total
                else 0.0
            ),
            "cases": case_results,
        }


def main() -> None:

    base_dir = (
        Path(__file__)
        .resolve()
        .parent
        .parent
    )

    evaluator = (
        SchemaGeneralizationEvaluator(
            cases_path=(
                base_dir
                / "evaluation"
                / "generalization_cases.json"
            )
        )
    )

    results = (
        evaluator.evaluate()
    )

    output_path = (
        base_dir
        / "evaluation"
        / "results"
        / "schema_generalization.json"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            results,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print(
        json.dumps(
            {
                "pass_rate": results[
                    "pass_rate"
                ],
                "passed_cases": results[
                    "passed_cases"
                ],
                "failed_cases": results[
                    "failed_cases"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()