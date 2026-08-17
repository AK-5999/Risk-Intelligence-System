from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.schemas import (
    FinalRiskOutput,
    FinalRiskRecord,
    RiskDraft,
)


class RiskValidator:
    """
    Phase 2 - Step 3: Final Structural Validation

    Responsibilities:
    - Validate complete generated risk drafts
    - Verify page exists in Phase-1 source
    - Verify block IDs belong to the source page
    - Check assignment description length
    - Assign deterministic risk IDs
    - Produce final risks.json
    """

    def __init__(
        self,
        *,
        parsed_input_path: Path,
        logger,
    ):
        self.parsed_input_path = (
            parsed_input_path
        )

        self.logger = logger

    # ------------------------------------------------------------------
    # SOURCE
    # ------------------------------------------------------------------

    def _load_source(
        self,
    ) -> dict[str, Any]:

        if not (
            self.parsed_input_path
            .exists()
        ):
            raise FileNotFoundError(
                f"Parsed source JSON not found: "
                f"{self.parsed_input_path}"
            )

        with self.parsed_input_path.open(
            "r",
            encoding="utf-8",
        ) as file:

            return json.load(
                file
            )

    @staticmethod
    def _source_index(
        source: dict[str, Any],
    ) -> dict[
        int,
        set[str],
    ]:

        index: dict[
            int,
            set[str],
        ] = {}

        for page in source.get(
            "pages",
            [],
        ):

            page_number = (
                page.get(
                    "page_number"
                )
            )

            if page_number is None:
                continue

            index[
                page_number
            ] = {
                block.get(
                    "block_id"
                )
                for block in page.get(
                    "blocks",
                    [],
                )
                if block.get(
                    "block_id"
                )
            }

        return index

    # ------------------------------------------------------------------
    # DESCRIPTION CHECK
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # VALIDATION
    # ------------------------------------------------------------------

    def validate(
        self,
        generated: dict[str, Any],
    ) -> FinalRiskOutput:

        self.logger.info(
            "STEP_3 | validation | STARTED"
        )

        source = (
            self._load_source()
        )

        source_index = (
            self._source_index(
                source
            )
        )

        contexts = (
            generated.get(
                "generation",
                {},
            ).get(
                "contexts",
                [],
            )
        )

        final_risks: list[
            FinalRiskRecord
        ] = []

        sequence = 1

        for context in contexts:

            source_type = (
                context.get(
                    "source_type",
                    ""
                )
            )

            source_topic = (
                context.get(
                    "topic"
                )
            )

            for risk_data in context.get(
                "risks",
                [],
            ):

                # --------------------------------------------------
                # Pydantic
                # --------------------------------------------------

                try:
                    draft = (
                        RiskDraft
                        .model_validate(
                            risk_data
                        )
                    )

                except Exception:

                    self.logger.exception(
                        "STEP_3 | schema_validation | "
                        "FAILED | title=%s",
                        risk_data.get(
                            "title"
                        ),
                    )

                    continue

                self.logger.info(
                    "STEP_3 | schema_validation | "
                    "PASS | title=%s",
                    draft.title,
                )

                # --------------------------------------------------
                # Page
                # --------------------------------------------------

                if (
                    draft.page
                    not in source_index
                ):

                    self.logger.warning(
                        "STEP_3 | page_validation | "
                        "FAILED | title=%s | page=%s",
                        draft.title,
                        draft.page,
                    )

                    continue

                # --------------------------------------------------
                # Block
                # --------------------------------------------------

                valid_blocks = (
                    source_index[
                        draft.page
                    ]
                )

                invalid_blocks = [
                    block_id
                    for block_id
                    in draft.source_block_ids
                    if block_id
                    not in valid_blocks
                ]

                if invalid_blocks:

                    self.logger.warning(
                        "STEP_3 | block_validation | "
                        "FAILED | title=%s | blocks=%s",
                        draft.title,
                        invalid_blocks,
                    )

                    continue

                # --------------------------------------------------
                # Description
                # --------------------------------------------------

                sentences = (
                    self._sentence_count(
                        draft.description
                    )
                )

                if not (
                    2
                    <= sentences
                    <= 3
                ):

                    self.logger.warning(
                        "STEP_3 | description_validation | "
                        "FAILED | title=%s | sentences=%s",
                        draft.title,
                        sentences,
                    )

                    continue

                # --------------------------------------------------
                # Final record
                # --------------------------------------------------

                risk_id = (
                    f"risk_{sequence:03d}"
                )

                sequence += 1

                final_risks.append(
                    FinalRiskRecord(
                        **draft.model_dump(),
                        risk_id=risk_id,
                        source_type=(
                            source_type
                        ),
                        source_topic=(
                            source_topic
                        ),
                    )
                )

        final_output = (
            FinalRiskOutput(
                document_id=(
                    source.get(
                        "document_id"
                    )
                ),
                company=(
                    "Vestas Wind Systems A/S"
                ),
                report_year=2025,
                risks=final_risks,
            )
        )

        self.logger.info(
            "STEP_3 | validation | SUCCESS | final_risks=%s",
            len(
                final_risks
            ),
        )

        return final_output

    # ------------------------------------------------------------------
    # SAVE
    # ------------------------------------------------------------------

    @staticmethod
    def save(
        output: FinalRiskOutput,
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
                output.model_dump(
                    mode="json"
                ),
                file,
                indent=2,
                ensure_ascii=False,
            )