from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class RiskCandidateExtractor:
    """
    Phase 2 - Step 1.5: Deterministic Risk Candidate Extraction

    Responsibilities:
    - Read risk_analysis.json produced by RiskAnalyzer
    - Convert explicit enterprise Main Risks into candidates
    - Inspect ONLY the financial risk/opportunity column of
      sustainability IRO tables
    - Exclude:
        * blank entries
        * immaterial entries
        * opportunities
    - Preserve source page, block, section and topic
    - Produce risk_candidates.json for the LLM generation stage

    No LLM is used here.

    Important design principle:
    Deterministic structure determines WHERE a risk can exist.
    The LLM is only used later to structure WHAT the risk means.
    """

    IMMATERIAL_PATTERNS = (
        "scored as immaterial",
        "considered immaterial",
        "assessed as immaterial",
        "not material",
    )

    OPPORTUNITY_PATTERN = re.compile(
        r"\bopportunit(?:y|ies)\b",
        flags=re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        input_path: Path,
        logger,
    ):
        self.input_path = input_path
        self.logger = logger

    # ------------------------------------------------------------------
    # INPUT
    # ------------------------------------------------------------------

    def load_input(
        self,
    ) -> dict[str, Any]:

        self.logger.info(
            "STEP_1_5 | candidate_extraction | input_load | STARTED"
        )

        self.logger.info(
            "STEP_1_5 | candidate_extraction | input_file=%s",
            self.input_path,
        )

        if not self.input_path.exists():
            raise FileNotFoundError(
                f"Risk analysis JSON not found: {self.input_path}"
            )

        with self.input_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        self.logger.info(
            "STEP_1_5 | candidate_extraction | input_load | SUCCESS"
        )

        return data

    # ------------------------------------------------------------------
    # NORMALIZATION
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_column_name(
        value: str,
    ) -> str:
        """
        Convert variations such as:

        impact_on_people_and_environment__name_and_description

        to a stable comparable representation.
        """

        value = value.strip().lower()

        value = re.sub(
            r"[^a-z0-9]+",
            "_",
            value,
        )

        value = re.sub(
            r"_+",
            "_",
            value,
        )

        return value.strip("_")

    @classmethod
    def _column_index(
        cls,
        columns: list[str],
        *,
        required_terms: tuple[str, ...],
    ) -> int | None:

        for index, column in enumerate(columns):

            normalised = cls._normalise_column_name(
                column
            )

            if all(
                term in normalised
                for term in required_terms
            ):
                return index

        return None

    # ------------------------------------------------------------------
    # FILTERING
    # ------------------------------------------------------------------

    @classmethod
    def _is_immaterial(
        cls,
        text: str,
    ) -> bool:

        lowered = text.lower()

        return any(
            pattern in lowered
            for pattern in cls.IMMATERIAL_PATTERNS
        )

    @classmethod
    def _is_opportunity(
        cls,
        text: str,
    ) -> bool:
        """
        The financial-side cell may contain either:

            risk
            opportunity

        A candidate explicitly described as an opportunity must
        not enter the risk-generation stage.
        """

        return bool(
            cls.OPPORTUNITY_PATTERN.search(
                text
            )
        )

    @staticmethod
    def _is_blank(
        text: Any,
    ) -> bool:

        if text is None:
            return True

        value = str(text).strip()

        return (
            not value
            or value.upper() == "N/A"
        )

    # ------------------------------------------------------------------
    # ENTERPRISE MAIN RISKS
    # ------------------------------------------------------------------

    def _extract_enterprise_candidates(
        self,
        enterprise: dict[str, Any] | None,
        candidates: list[dict[str, Any]],
    ) -> None:
        """
        Convert an explicit enterprise principal-risk table into
        deterministic risk candidates.
    
        Expected structure:
        - The first column describes attributes of each risk.
        - Remaining columns represent declared principal risks.
        - Common row attributes may include description,
          potential impact, and mitigation information.
    
        Because the source table explicitly declares these columns
        as principal risks, no probabilistic filtering is required
        at this stage.
        """

        if not enterprise:
            return

        section = enterprise.get(
            "section",
            "Risk management",
        )

        topic = enterprise.get(
            "subsection",
            "Main risks",
        )

        for table in enterprise.get(
            "tables",
            [],
        ):
            columns = table.get(
                "columns",
                [],
            )

            rows = table.get(
                "rows",
                [],
            )

            if len(columns) <= 1:
                continue

            # Build:
            #
            # {
            #   "description": [...],
            #   "potential impact": [...],
            #   "how we manage it": [...]
            # }

            row_map: dict[
                str,
                list[Any],
            ] = {}

            for row in rows:

                if not row:
                    continue

                attribute = (
                    str(row[0])
                    .strip()
                    .lower()
                )

                row_map[
                    attribute
                ] = row

            for column_index in range(
                1,
                len(columns),
            ):

                risk_title = str(
                    columns[column_index]
                ).strip()

                if not risk_title:
                    continue

                description = (
                    self._value_from_row(
                        row_map,
                        "description",
                        column_index,
                    )
                )

                potential_impact = (
                    self._value_from_row(
                        row_map,
                        "potential impact",
                        column_index,
                    )
                )

                mitigation = (
                    self._value_from_row(
                        row_map,
                        "how we manage it",
                        column_index,
                    )
                )

                candidate_id = (
                    f"enterprise_{len(candidates) + 1:03d}"
                )

                candidates.append(
                    {
                        "candidate_id": candidate_id,
                        "candidate_type": (
                            "enterprise_principal_risk"
                        ),
                        "source_type": (
                            "enterprise_main_risks"
                        ),
                        "section": section,
                        "topic": topic,
                        "page": table.get(
                            "page"
                        ),
                        "block_id": table.get(
                            "block_id"
                        ),
                        "materiality_type": None,
                        "sub_topic": None,
                        "value_chain": None,
                        "source_title": (
                            risk_title
                        ),
                        "candidate_text": (
                            description
                        ),
                        "potential_impact": (
                            potential_impact
                        ),
                        "mitigation_source": (
                            mitigation
                            or None
                        ),
                    }
                )

                self.logger.info(
                    "STEP_1_5 | candidate_created | "
                    "id=%s | type=enterprise | "
                    "page=%s | title=%s",
                    candidate_id,
                    table.get("page"),
                    risk_title,
                )

    @staticmethod
    def _value_from_row(
        row_map: dict[str, list[Any]],
        key: str,
        column_index: int,
    ) -> str:

        row = row_map.get(
            key
        )

        if not row:
            return ""

        if column_index >= len(row):
            return ""

        value = row[
            column_index
        ]

        return (
            str(value).strip()
            if value is not None
            else ""
        )

    # ------------------------------------------------------------------
    # MATERIAL IRO CANDIDATES
    # ------------------------------------------------------------------

    def _extract_material_candidates(
        self,
        material: dict[str, Any],
        candidates: list[dict[str, Any]],
        excluded: list[dict[str, Any]],
    ) -> None:

        section = material.get(
            "section",
            "Material impacts, risks, and opportunities",
        )

        for topic in material.get(
            "topics",
            [],
        ):

            topic_code = topic.get(
                "topic_code",
                ""
            )

            topic_name = topic.get(
                "topic_name",
                ""
            )

            topic_label = (
                f"{topic_code} {topic_name}"
            ).strip()

            for table in topic.get(
                "tables",
                [],
            ):

                columns = table.get(
                    "columns",
                    [],
                )

                rows = table.get(
                    "rows",
                    [],
                )

                # --------------------------------------------------
                # Locate semantic columns dynamically.
                # --------------------------------------------------

                financial_index = (
                    self._column_index(
                        columns,
                        required_terms=(
                            "financial",
                            "risk",
                            "opportunity",
                            "name",
                            "description",
                        ),
                    )
                )

                if financial_index is None:

                    self.logger.warning(
                        "STEP_1_5 | table_skip | "
                        "reason=no_financial_risk_column | "
                        "topic=%s | page=%s | block=%s",
                        topic_label,
                        table.get("page"),
                        table.get("block_id"),
                    )

                    continue

                materiality_index = (
                    self._column_index(
                        columns,
                        required_terms=(
                            "materiality",
                            "type",
                        ),
                    )
                )

                sub_topic_index = (
                    self._column_index(
                        columns,
                        required_terms=(
                            "sub",
                            "topic",
                        ),
                    )
                )

                value_chain_index = (
                    self._column_index(
                        columns,
                        required_terms=(
                            "financial",
                            "value",
                            "chain",
                        ),
                    )
                )

                for row_index, row in enumerate(
                    rows
                ):

                    if (
                        financial_index
                        >= len(row)
                    ):
                        continue

                    financial_text = str(
                        row[
                            financial_index
                        ]
                        or ""
                    ).strip()

                    reason = (
                        self._exclusion_reason(
                            financial_text
                        )
                    )

                    if reason:

                        excluded.append(
                            {
                                "topic": topic_label,
                                "page": table.get(
                                    "page"
                                ),
                                "block_id": table.get(
                                    "block_id"
                                ),
                                "row_index": row_index,
                                "text": financial_text,
                                "reason": reason,
                            }
                        )

                        self.logger.info(
                            "STEP_1_5 | candidate_excluded | "
                            "topic=%s | page=%s | "
                            "block=%s | row=%s | reason=%s",
                            topic_label,
                            table.get("page"),
                            table.get("block_id"),
                            row_index,
                            reason,
                        )

                        continue

                    materiality = (
                        self._safe_row_value(
                            row,
                            materiality_index,
                        )
                    )

                    sub_topic = (
                        self._safe_row_value(
                            row,
                            sub_topic_index,
                        )
                    )

                    value_chain = (
                        self._safe_row_value(
                            row,
                            value_chain_index,
                        )
                    )

                    candidate_id = (
                        f"iro_{len(candidates) + 1:03d}"
                    )

                    candidates.append(
                        {
                            "candidate_id": (
                                candidate_id
                            ),
                            "candidate_type": (
                                "material_financial_risk"
                            ),
                            "source_type": (
                                "material_iro"
                            ),
                            "section": section,
                            "topic": topic_label,
                            "page": table.get(
                                "page"
                            ),
                            "block_id": table.get(
                                "block_id"
                            ),
                            "materiality_type": (
                                materiality
                                or None
                            ),
                            "sub_topic": (
                                sub_topic
                                or None
                            ),
                            "value_chain": (
                                value_chain
                                or None
                            ),

                            # For material-risk tables, the source
                            # title and description were flattened
                            # into the same normalized cell.
                            #
                            # We therefore allow the LLM to recover
                            # the concise source title from this
                            # already-filtered financial-risk cell.
                            "source_title": None,

                            "candidate_text": (
                                financial_text
                            ),

                            "potential_impact": None,

                            # Pages 71-74 do not provide mitigation
                            # actions for these rows in the scoped
                            # source.
                            "mitigation_source": None,
                        }
                    )

                    self.logger.info(
                        "STEP_1_5 | candidate_created | "
                        "id=%s | type=material_financial_risk | "
                        "topic=%s | page=%s | block=%s",
                        candidate_id,
                        topic_label,
                        table.get("page"),
                        table.get("block_id"),
                    )

    def _exclusion_reason(
        self,
        text: str,
    ) -> str | None:

        if self._is_blank(
            text
        ):
            return "blank_financial_cell"

        if self._is_immaterial(
            text
        ):
            return "immaterial"

        if self._is_opportunity(
            text
        ):
            return "financial_opportunity"

        return None

    @staticmethod
    def _safe_row_value(
        row: list[Any],
        index: int | None,
    ) -> str:

        if index is None:
            return ""

        if index >= len(row):
            return ""

        value = row[index]

        return (
            str(value).strip()
            if value is not None
            else ""
        )

    # ------------------------------------------------------------------
    # MAIN
    # ------------------------------------------------------------------

    def extract(
        self,
    ) -> dict[str, Any]:

        self.logger.info(
            "STEP_1_5 | candidate_extraction | STARTED"
        )

        data = self.load_input()

        risk_analysis = data.get(
            "risk_analysis",
            {},
        )

        candidates: list[
            dict[str, Any]
        ] = []

        excluded: list[
            dict[str, Any]
        ] = []

        self._extract_enterprise_candidates(
            risk_analysis.get(
                "enterprise_risks"
            ),
            candidates,
        )

        self._extract_material_candidates(
            risk_analysis.get(
                "material_impacts_risks_and_opportunities",
                {},
            ),
            candidates,
            excluded,
        )

        enterprise_count = sum(
            1
            for candidate in candidates
            if candidate[
                "candidate_type"
            ]
            == "enterprise_principal_risk"
        )

        material_count = sum(
            1
            for candidate in candidates
            if candidate[
                "candidate_type"
            ]
            == "material_financial_risk"
        )

        result = {
            "document": data.get(
                "document",
                {},
            ),
            "candidate_analysis": {
                "candidate_count": len(
                    candidates
                ),
                "enterprise_candidate_count": (
                    enterprise_count
                ),
                "material_candidate_count": (
                    material_count
                ),
                "excluded_count": len(
                    excluded
                ),
                "candidates": candidates,
                "excluded_items": excluded,
            },
        }

        self.logger.info(
            "STEP_1_5 | candidate_extraction | SUCCESS | "
            "candidates=%s | enterprise=%s | "
            "material=%s | excluded=%s",
            len(candidates),
            enterprise_count,
            material_count,
            len(excluded),
        )

        return result

    # ------------------------------------------------------------------
    # SAVE
    # ------------------------------------------------------------------

    def save(
        self,
        data: dict[str, Any],
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
                data,
                file,
                indent=2,
                ensure_ascii=False,
            )

        self.logger.info(
            "STEP_1_5 | candidate_output | SUCCESS | output=%s",
            output_path,
        )