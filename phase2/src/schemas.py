from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class RiskCategory(str, Enum):
    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    REGULATORY = "regulatory"
    MARKET = "market"
    CLIMATE = "climate"
    CYBER = "cyber"
    SUPPLY_CHAIN = "supply_chain"
    GOVERNANCE = "governance"
    WORKFORCE = "workforce"
    GEOPOLITICAL = "geopolitical"
    OTHER = "other"


# ======================================================================
# LLM CONTRACT
# ======================================================================


class GeneratedRisk(BaseModel):
    """
    Minimal information the LLM is allowed to generate.

    Page, section, source blocks and mitigation are NOT generated
    by the LLM anymore.

    Those values already exist deterministically in the candidate
    object and will be attached by RiskGenerator.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    candidate_id: str = Field(
        min_length=2
    )

    title: str = Field(
        min_length=2
    )

    description: str = Field(
        min_length=20
    )

    category: RiskCategory

    @field_validator(
        "candidate_id",
        "title",
        "description",
        mode="before",
    )
    @classmethod
    def strip_text(
        cls,
        value: Any,
    ) -> Any:

        if isinstance(
            value,
            str,
        ):
            return value.strip()

        return value


class GeneratedRiskBatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    risks: list[
        GeneratedRisk
    ]

    @field_validator(
        "risks",
        mode="before",
    )
    @classmethod
    def parse_stringified_risks(
        cls,
        value: Any,
    ) -> Any:

        if not isinstance(
            value,
            list,
        ):
            return value

        parsed_items = []

        for item in value:

            if isinstance(
                item,
                dict,
            ):
                parsed_items.append(
                    item
                )
                continue

            if isinstance(
                item,
                str,
            ):

                try:
                    parsed_items.append(
                        json.loads(
                            item.strip()
                        )
                    )

                except json.JSONDecodeError:
                    parsed_items.append(
                        item
                    )

                continue

            parsed_items.append(
                item
            )

        return parsed_items


# ======================================================================
# PIPELINE DRAFT
# ======================================================================


class RiskDraft(BaseModel):
    """
    Complete grounded risk record after LLM generation and before
    the final risk_id is assigned.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    title: str = Field(
        min_length=2
    )

    description: str = Field(
        min_length=20
    )

    category: RiskCategory

    section: str = Field(
        min_length=2
    )

    page: int = Field(
        ge=1
    )

    mitigation: str | None = None

    source_block_ids: list[
        str
    ] = Field(
        default_factory=list
    )


# ======================================================================
# FINAL OUTPUT
# ======================================================================


class FinalRiskRecord(
    RiskDraft
):
    risk_id: str

    source_type: str

    source_topic: str | None = None


class FinalRiskOutput(BaseModel):
    document_id: str | None

    company: str | None = None

    report_year: int | None = None

    risks: list[
        FinalRiskRecord
    ]