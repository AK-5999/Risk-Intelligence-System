from __future__ import annotations

from typing import Any


class DocumentEvaluator:
    """
    Evaluate canonical document output against
    manually created golden expectations.

    Evaluation focuses on information required
    by downstream Risk Intelligence processing.
    """

    def evaluate_page(
        self,
        actual_page: dict[str, Any],
        golden: dict[str, Any],
    ) -> dict[str, Any]:

        metrics: dict[str, Any] = {}

        metrics["heading_recall"] = (
            self._evaluate_headings(
                actual_page,
                golden,
            )
        )

        metrics["text_fragment_recall"] = (
            self._evaluate_text_fragments(
                actual_page,
                golden,
            )
        )

        metrics["table_metrics"] = (
            self._evaluate_tables(
                actual_page,
                golden,
            )
        )

        metrics["provenance_coverage"] = (
            self._evaluate_provenance(
                actual_page,
                golden,
            )
        )

        scores = [
            metrics["heading_recall"]["score"],
            metrics["text_fragment_recall"]["score"],
            metrics["table_metrics"]["score"],
            metrics["provenance_coverage"]["score"],
        ]

        metrics["overall_score"] = (
            sum(scores)
            / len(scores)
            if scores
            else 0.0
        )

        return {
            "page_number": golden.get(
                "page_number"
            ),
            "description": golden.get(
                "description"
            ),
            "metrics": metrics,
        }

    # =========================================================
    # HEADINGS
    # =========================================================

    def _evaluate_headings(
        self,
        page: dict[str, Any],
        golden: dict[str, Any],
    ) -> dict[str, Any]:

        expected = golden.get(
            "expected_headings",
            [],
        )

        if not expected:
            return {
                "score": 1.0,
                "expected": 0,
                "matched": 0,
                "missing": [],
            }

        actual = [
            block.get("text", "").strip()
            for block in page.get(
                "blocks",
                [],
            )
            if block.get("type")
            == "heading"
        ]

        actual_normalized = {
            value.lower()
            for value in actual
        }

        missing = []

        for heading in expected:

            if (
                heading.lower()
                not in actual_normalized
            ):
                missing.append(
                    heading
                )

        matched = (
            len(expected)
            - len(missing)
        )

        score = (
            matched / len(expected)
        )

        return {
            "score": score,
            "expected": len(expected),
            "matched": matched,
            "missing": missing,
        }

    # =========================================================
    # TEXT
    # =========================================================

    def _evaluate_text_fragments(
        self,
        page: dict[str, Any],
        golden: dict[str, Any],
    ) -> dict[str, Any]:

        expected = golden.get(
            "required_text_fragments",
            [],
        )

        # Include normal text and table cells.
        actual_text_parts = []

        for block in page.get(
            "blocks",
            [],
        ):

            block_text = block.get(
                "text",
                "",
            )

            if block_text:
                actual_text_parts.append(
                    block_text
                )

            table = block.get(
                "table"
            )

            if table:

                for column in table.get(
                    "columns",
                    [],
                ):
                    actual_text_parts.append(
                        str(column)
                    )

                for row in table.get(
                    "rows",
                    [],
                ):

                    for cell in row:
                        actual_text_parts.append(
                            str(cell)
                        )

        actual_text = (
            " ".join(actual_text_parts)
            .lower()
        )

        if not expected:

            return {
                "score": 1.0,
                "expected": 0,
                "matched": 0,
                "missing": [],
            }

        missing = []

        for fragment in expected:

            if (
                fragment.lower()
                not in actual_text
            ):
                missing.append(
                    fragment
                )

        matched = (
            len(expected)
            - len(missing)
        )

        return {
            "score": (
                matched / len(expected)
            ),
            "expected": len(expected),
            "matched": matched,
            "missing": missing,
        }

    # =========================================================
    # TABLES
    # =========================================================

    def _evaluate_tables(
        self,
        page: dict[str, Any],
        golden: dict[str, Any],
    ) -> dict[str, Any]:

        expected_tables = (
            golden.get(
                "expected_tables",
                [],
            )
        )

        actual_tables = [
            block["table"]
            for block in page.get(
                "blocks",
                [],
            )
            if (
                block.get("type")
                == "table"
                and block.get("table")
            )
        ]

        if not expected_tables:

            return {
                "score": 1.0,
                "expected_tables": 0,
                "actual_tables": (
                    len(actual_tables)
                ),
                "details": [],
            }

        details = []

        total_subscores = []

        for index, expected in enumerate(
            expected_tables
        ):

            if index >= len(
                actual_tables
            ):

                details.append(
                    {
                        "table_index": index,
                        "detected": False,
                        "score": 0.0,
                    }
                )

                total_subscores.append(
                    0.0
                )

                continue

            actual = actual_tables[
                index
            ]

            result = (
                self._evaluate_single_table(
                    actual,
                    expected,
                )
            )

            details.append(
                result
            )

            total_subscores.append(
                result["score"]
            )

        score = (
            sum(total_subscores)
            / len(total_subscores)
            if total_subscores
            else 0.0
        )

        return {
            "score": score,
            "expected_tables": (
                len(expected_tables)
            ),
            "actual_tables": (
                len(actual_tables)
            ),
            "details": details,
        }

    def _evaluate_single_table(
        self,
        actual: dict[str, Any],
        expected: dict[str, Any],
    ) -> dict[str, Any]:

        checks = {}

        # -----------------------------------------------------
        # TABLE SHAPE
        # -----------------------------------------------------

        expected_rows = expected.get(
            "row_count"
        )

        expected_columns = expected.get(
            "column_count"
        )

        actual_rows = actual.get(
            "row_count",
            len(
                actual.get(
                    "rows",
                    [],
                )
            ),
        )

        actual_columns = actual.get(
            "column_count",
            len(
                actual.get(
                    "columns",
                    [],
                )
            ),
        )

        checks["row_count"] = {
            "expected": expected_rows,
            "actual": actual_rows,
            "passed": (
                expected_rows is None
                or
                expected_rows
                == actual_rows
            ),
        }

        checks["column_count"] = {
            "expected": expected_columns,
            "actual": actual_columns,
            "passed": (
                expected_columns is None
                or
                expected_columns
                == actual_columns
            ),
        }

        # -----------------------------------------------------
        # HEADERS
        # -----------------------------------------------------

        expected_headers = expected.get(
            "columns",
            [],
        )

        actual_headers = actual.get(
            "columns",
            [],
        )

        if expected_headers:

            headers_passed = (
                [
                    str(x).strip().lower()
                    for x
                    in actual_headers
                ]
                ==
                [
                    str(x).strip().lower()
                    for x
                    in expected_headers
                ]
            )

        else:
            headers_passed = True

        checks["headers"] = {
            "expected": expected_headers,
            "actual": actual_headers,
            "passed": headers_passed,
        }

        # -----------------------------------------------------
        # ROW LABELS
        # -----------------------------------------------------

        expected_labels = expected.get(
            "required_row_labels",
            [],
        )

        actual_labels = [
            str(row[0]).strip()
            for row in actual.get(
                "rows",
                [],
            )
            if row
        ]

        missing_labels = [
            label
            for label in expected_labels
            if label.lower()
            not in {
                value.lower()
                for value in actual_labels
            }
        ]

        checks["row_labels"] = {
            "expected": expected_labels,
            "actual": actual_labels,
            "missing": missing_labels,
            "passed": (
                not missing_labels
            ),
        }

        passed = sum(
            1
            for check in checks.values()
            if check["passed"]
        )

        score = (
            passed / len(checks)
            if checks
            else 1.0
        )

        return {
            "detected": True,
            "score": score,
            "checks": checks,
        }

    # =========================================================
    # PROVENANCE
    # =========================================================

    def _evaluate_provenance(
        self,
        page: dict[str, Any],
        golden: dict[str, Any],
    ) -> dict[str, Any]:

        if not golden.get(
            "provenance_required",
            False,
        ):

            return {
                "score": 1.0,
                "required": False,
            }

        blocks = page.get(
            "blocks",
            [],
        )

        if not blocks:

            return {
                "score": 0.0,
                "required": True,
                "blocks": 0,
                "with_provenance": 0,
            }

        blocks_with_provenance = (
            sum(
                1
                for block in blocks
                if block.get(
                    "provenance"
                )
            )
        )

        return {
            "score": (
                blocks_with_provenance
                / len(blocks)
            ),
            "required": True,
            "blocks": len(blocks),
            "with_provenance": (
                blocks_with_provenance
            ),
        }