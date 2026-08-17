from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class RiskEvaluator:
    """
    Deterministic evaluator for Phase 2 risk extraction.

    Evaluates:
    - Expected risk presence
    - Missing risks
    - Unexpected generated risks / false positives
    - Category accuracy
    - Page accuracy
    - Section accuracy
    - Mitigation presence
    - Description sentence-count requirement
    - Known failure-case diagnostics
    """

    def __init__(
        self,
        *,
        generated_path: Path,
        golden_path: Path,
        failure_path: Path,
        logger=None,
    ):
        self.generated_path = generated_path
        self.golden_path = golden_path
        self.failure_path = failure_path
        self.logger = logger

    # --------------------------------------------------------------
    # INPUT
    # --------------------------------------------------------------

    @staticmethod
    def _load_json(
        path: Path,
    ) -> dict[str, Any]:

        if not path.exists():
            raise FileNotFoundError(
                f"Evaluation file not found: {path}"
            )

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(
                file
            )

    # --------------------------------------------------------------
    # NORMALIZATION
    # --------------------------------------------------------------

    @staticmethod
    def _normalize_title(
        title: str,
    ) -> str:
        """
        Normalize titles for deterministic comparison.
        """

        title = (
            str(title)
            .lower()
            .strip()
        )

        title = re.sub(
            r"[^a-z0-9\s]",
            " ",
            title,
        )

        title = re.sub(
            r"\s+",
            " ",
            title,
        )

        return title.strip()

    @staticmethod
    def _sentence_count(
        text: str,
    ) -> int:

        if not text:
            return 0

        parts = re.split(
            r"(?<=[.!?])\s+",
            text.strip(),
        )

        return len(
            [
                item
                for item in parts
                if item.strip()
            ]
        )

    # --------------------------------------------------------------
    # EVALUATION
    # --------------------------------------------------------------

    def evaluate(
        self,
    ) -> dict[str, Any]:

        generated = self._load_json(
            self.generated_path
        )

        golden = self._load_json(
            self.golden_path
        )

        failures = self._load_json(
            self.failure_path
        )

        generated_risks = generated.get(
            "risks",
            [],
        )

        expected_risks = golden.get(
            "risks",
            [],
        )

        failure_cases = failures.get(
            "cases",
            [],
        )

        # ----------------------------------------------------------
        # Index generated risks
        # ----------------------------------------------------------

        generated_index = {
            self._normalize_title(
                risk.get(
                    "title",
                    "",
                )
            ): risk
            for risk in generated_risks
            if risk.get(
                "title"
            )
        }

        # ----------------------------------------------------------
        # Index golden risks
        # ----------------------------------------------------------

        expected_index = {
            self._normalize_title(
                risk.get(
                    "title",
                    "",
                )
            ): risk
            for risk in expected_risks
            if risk.get(
                "title"
            )
        }

        results = {
            "expected_total": len(
                expected_risks
            ),
            "generated_total": len(
                generated_risks
            ),
            "matched": [],
            "missing": [],
            "false_positives": [],
            "field_failures": [],
            "known_failure_diagnostics": [],
        }

        # ==========================================================
        # 1. EXPECTED RISK CHECKS
        # ==========================================================

        for expected in expected_risks:

            expected_title = (
                self._normalize_title(
                    expected[
                        "title"
                    ]
                )
            )

            actual = generated_index.get(
                expected_title
            )

            # ------------------------------------------------------
            # Missing expected risk
            # ------------------------------------------------------

            if actual is None:

                results[
                    "missing"
                ].append(
                    {
                        "gold_id": expected[
                            "id"
                        ],
                        "title": expected[
                            "title"
                        ],
                    }
                )

                continue

            # ------------------------------------------------------
            # Field-level comparison
            # ------------------------------------------------------

            match_result = {
                "gold_id": expected[
                    "id"
                ],
                "title": expected[
                    "title"
                ],
                "page_match": (
                    actual.get(
                        "page"
                    )
                    == expected.get(
                        "page"
                    )
                ),
                "category_match": (
                    actual.get(
                        "category"
                    )
                    == expected.get(
                        "category"
                    )
                ),
                "section_match": (
                    actual.get(
                        "section"
                    )
                    == expected.get(
                        "section"
                    )
                ),
            }

            mitigation_expected = (
                expected.get(
                    "mitigation_expected",
                    False,
                )
            )

            mitigation_present = bool(
                actual.get(
                    "mitigation"
                )
            )

            match_result[
                "mitigation_match"
            ] = (
                mitigation_present
                == mitigation_expected
            )

            sentence_count = (
                self._sentence_count(
                    actual.get(
                        "description",
                        "",
                    )
                )
            )

            match_result[
                "description_sentence_count"
            ] = sentence_count

            match_result[
                "description_length_valid"
            ] = (
                2
                <= sentence_count
                <= 3
            )

            results[
                "matched"
            ].append(
                match_result
            )

            for field in [
                "page_match",
                "category_match",
                "section_match",
                "mitigation_match",
                "description_length_valid",
            ]:

                if not match_result[
                    field
                ]:

                    results[
                        "field_failures"
                    ].append(
                        {
                            "title": expected[
                                "title"
                            ],
                            "field": field,
                            "expected": (
                                self._expected_field_value(
                                    expected,
                                    field,
                                )
                            ),
                            "actual": (
                                self._actual_field_value(
                                    actual,
                                    field,
                                    sentence_count,
                                )
                            ),
                        }
                    )

        # ==========================================================
        # 2. TRUE FALSE-POSITIVE DETECTION
        # ==========================================================
        #
        # Any generated title not present in the golden set is an FP.
        #
        # failure_cases.json is NOT used to define precision.
        # ==========================================================

        expected_titles = set(
            expected_index.keys()
        )

        generated_titles = set(
            generated_index.keys()
        )

        unexpected_titles = (
            generated_titles
            - expected_titles
        )

        for normalized_title in sorted(
            unexpected_titles
        ):

            risk = generated_index[
                normalized_title
            ]

            results[
                "false_positives"
            ].append(
                {
                    "title": risk.get(
                        "title"
                    ),
                    "category": risk.get(
                        "category"
                    ),
                    "page": risk.get(
                        "page"
                    ),
                    "section": risk.get(
                        "section"
                    ),
                }
            )

        # ==========================================================
        # 3. KNOWN FAILURE-CASE DIAGNOSTICS
        # ==========================================================
        #
        # These cases explain known failure modes.
        # They do NOT control precision.
        # ==========================================================

        for failure in failure_cases:

            normalized = (
                self._normalize_title(
                    failure.get(
                        "title",
                        "",
                    )
                )
            )

            present = (
                normalized
                in generated_index
            )

            results[
                "known_failure_diagnostics"
            ].append(
                {
                    "failure_id": failure.get(
                        "id"
                    ),
                    "title": failure.get(
                        "title"
                    ),
                    "failure_type": failure.get(
                        "failure_type"
                    ),
                    "generated": present,
                    "status": (
                        "FAILED"
                        if present
                        else "PASSED"
                    ),
                }
            )

        # ==========================================================
        # 4. METRICS
        # ==========================================================

        matched_count = len(
            results[
                "matched"
            ]
        )

        missing_count = len(
            results[
                "missing"
            ]
        )

        false_positive_count = len(
            results[
                "false_positives"
            ]
        )

        expected_total = len(
            expected_risks
        )

        generated_total = len(
            generated_risks
        )

        recall = (
            matched_count
            / expected_total
            if expected_total
            else 0.0
        )

        precision_denominator = (
            matched_count
            + false_positive_count
        )

        precision = (
            matched_count
            / precision_denominator
            if precision_denominator
            else 0.0
        )

        if precision + recall:

            f1 = (
                2
                * precision
                * recall
                / (
                    precision
                    + recall
                )
            )

        else:

            f1 = 0.0

        field_failure_count = len(
            results[
                "field_failures"
            ]
        )

        results[
            "metrics"
        ] = {
            "precision": round(
                precision,
                4,
            ),
            "recall": round(
                recall,
                4,
            ),
            "f1": round(
                f1,
                4,
            ),
            "matched_count": (
                matched_count
            ),
            "missing_count": (
                missing_count
            ),
            "false_positive_count": (
                false_positive_count
            ),
            "field_failure_count": (
                field_failure_count
            ),
            "generated_total": (
                generated_total
            ),
        }

        # ==========================================================
        # 5. OVERALL STATUS
        # ==========================================================

        results[
            "status"
        ] = (
            "PASSED"
            if (
                missing_count == 0
                and false_positive_count == 0
                and field_failure_count == 0
            )
            else "FAILED"
        )

        return results

    # --------------------------------------------------------------
    # FIELD DIAGNOSTICS
    # --------------------------------------------------------------

    @staticmethod
    def _expected_field_value(
        expected: dict[str, Any],
        field: str,
    ) -> Any:

        mapping = {
            "page_match": (
                expected.get(
                    "page"
                )
            ),
            "category_match": (
                expected.get(
                    "category"
                )
            ),
            "section_match": (
                expected.get(
                    "section"
                )
            ),
            "mitigation_match": (
                expected.get(
                    "mitigation_expected",
                    False,
                )
            ),
            "description_length_valid": (
                "2-3 sentences"
            ),
        }

        return mapping.get(
            field
        )

    @staticmethod
    def _actual_field_value(
        actual: dict[str, Any],
        field: str,
        sentence_count: int,
    ) -> Any:

        mapping = {
            "page_match": (
                actual.get(
                    "page"
                )
            ),
            "category_match": (
                actual.get(
                    "category"
                )
            ),
            "section_match": (
                actual.get(
                    "section"
                )
            ),
            "mitigation_match": bool(
                actual.get(
                    "mitigation"
                )
            ),
            "description_length_valid": (
                sentence_count
            ),
        }

        return mapping.get(
            field
        )

    # --------------------------------------------------------------
    # SAVE
    # --------------------------------------------------------------

    @staticmethod
    def save(
        results: dict[str, Any],
        output_path: Path,
    ) -> None:

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


def main() -> None:

    base_dir = (
        Path(__file__)
        .resolve()
        .parent
        .parent
    )

    evaluator = RiskEvaluator(
        generated_path=(
            base_dir
            / "output"
            / "final_risks.json"
        ),
        golden_path=(
            base_dir
            / "evaluation"
            / "golden_set.json"
        ),
        failure_path=(
            base_dir
            / "evaluation"
            / "failure_cases.json"
        ),
    )

    results = (
        evaluator.evaluate()
    )

    output_path = (
        base_dir
        / "evaluation"
        / "results"
        / "evaluation_results.json"
    )

    evaluator.save(
        results,
        output_path,
    )

    print(
        "\nGolden-set evaluation"
    )

    print(
        "---------------------"
    )

    print(
        json.dumps(
            results[
                "metrics"
            ],
            indent=2,
        )
    )

    print(
        "\nOverall status:",
        results[
            "status"
        ],
    )

    print(
        "\nResults saved to:",
        output_path,
    )


if __name__ == "__main__":
    main()