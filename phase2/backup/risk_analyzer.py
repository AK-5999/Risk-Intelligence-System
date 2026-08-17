from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# document order sorting
# challange: h1,h2,t1,t2 --> h1: {}, h2:t1, {}:t2
class RiskAnalyzer:
    """
    Phase 2 - Step 1: Risk Analysis

    Responsibilities:
    - Read manually validated Phase-1 JSON
    - Identify relevant sections
    - Reconstruct section/topic/table hierarchy
    - Preserve page/block traceability
    - Produce a compact JSON for the generation stage

    No LLM is used here.
    """

    MATERIAL_SECTION = "Material impacts, risks, and opportunities"
    RISK_SECTION = "Risk management"

    # ESRS / sustainability topic headings such as:
    # E1 Climate Change
    # E4 Biodiversity and ecosystems
    # E5 Circular economy and resource use
    # S1 Own Workforce
    # S2 Workers in the value chain
    # S3 Affected communities
    # G1 Business Conduct
    TOPIC_PATTERN = re.compile(
        r"^(E|S|G)\d+\s+.+$",
        flags=re.IGNORECASE,
    )

    IGNORED_HEADINGS = {
        "Sub-topic",
        "Impacts on people and environment",
        "Financial risks or opportunities",
    }

    def __init__(self, input_path: Path, logger):
        self.input_path = input_path
        self.logger = logger

    def load_input(self) -> dict[str, Any]:
        self.logger.info("STEP_1 | input_load | STARTED")
        self.logger.info("STEP_1 | input_file=%s", self.input_path)

        if not self.input_path.exists():
            self.logger.error(
                "STEP_1 | input_load | FAILED | file_not_found=%s",
                self.input_path,
            )
            raise FileNotFoundError(
                f"Input JSON not found: {self.input_path}"
            )

        with self.input_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        self.logger.info(
            "STEP_1 | input_load | SUCCESS | pages=%s",
            len(data.get("pages", [])),
        )

        return data

    @staticmethod
    def _get_heading_text(block: dict[str, Any]) -> str | None:
        if block.get("type") != "heading":
            return None

        text = block.get("text", "").strip()

        return text or None

    @classmethod
    def _is_topic_heading(cls, heading: str) -> bool:
        return bool(cls.TOPIC_PATTERN.match(heading))

    @staticmethod
    def _split_topic(heading: str) -> tuple[str, str]:
        """
        Example:
            'E1 Climate Change'
        ->
            ('E1', 'Climate Change')
        """
        parts = heading.split(maxsplit=1)

        topic_code = parts[0]
        topic_name = parts[1] if len(parts) > 1 else ""

        return topic_code, topic_name

    @staticmethod
    def _serialize_table(
        page_number: int,
        block: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Preserve table content and traceability while removing
        unrelated parser-level metadata.
        """
        return {
            "page": page_number,
            "block_id": block.get("block_id"),
            "columns": block.get("table", {}).get("columns", []),
            "rows": block.get("table", {}).get("rows", []),
            "row_count": block.get("table", {}).get("row_count", 0),
            "column_count": block.get("table", {}).get(
                "column_count", 0
            ),
            "normalized": block.get("table", {}).get(
                "normalized", False
            ),
            "provenance": block.get("provenance", []),
        }

    def _extract_enterprise_risks(
        self,
        pages: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """
        Extract the explicit 'Main risks' structure from page 51.
        """

        result = {
            "section": self.RISK_SECTION,
            "subsection": "Main risks",
            "pages": [],
            "tables": [],
        }

        for page in pages:
            page_number = page.get("page_number")

            if page_number not in {50, 51}:
                continue

            result["pages"].append(page_number)

            for block in page.get("blocks", []):
                if block.get("type") != "table":
                    continue

                table = block.get("table")

                if not table:
                    continue

                result["tables"].append(
                    self._serialize_table(
                        page_number=page_number,
                        block=block,
                    )
                )

                self.logger.info(
                    "STEP_1 | enterprise_table | "
                    "page=%s | block=%s | rows=%s",
                    page_number,
                    block.get("block_id"),
                    table.get("row_count"),
                )

        if not result["tables"]:
            self.logger.warning(
                "STEP_1 | enterprise_risks | no tables found"
            )
            return None

        return result

    def _extract_material_topics(
        self,
        pages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Reconstruct:

        Material impacts, risks, and opportunities
        ├── E1 Climate Change
        ├── E4 Biodiversity and ecosystems
        ...
        """

        output = {
            "section": self.MATERIAL_SECTION,
            "topics": [],
        }

        current_topic: dict[str, Any] | None = None

        for page in pages:
            page_number = page.get("page_number")

            if page_number not in {71, 72, 73, 74}:
                continue

            blocks = page.get("blocks", [])

            for block in blocks:
                heading = self._get_heading_text(block)

                if heading:
                    if heading in self.IGNORED_HEADINGS:
                        continue

                    if self._is_topic_heading(heading):
                        topic_code, topic_name = self._split_topic(
                            heading
                        )

                        current_topic = {
                            "topic_code": topic_code,
                            "topic_name": topic_name,
                            "pages": [page_number],
                            "tables": [],
                        }

                        output["topics"].append(current_topic)

                        self.logger.info(
                            "STEP_1 | topic_detected | "
                            "page=%s | code=%s | topic=%s",
                            page_number,
                            topic_code,
                            topic_name,
                        )

                        continue

                if block.get("type") != "table":
                    continue

                table = block.get("table")

                if not table:
                    continue

                if current_topic is None:
                    self.logger.warning(
                        "STEP_1 | orphan_table | "
                        "page=%s | block=%s",
                        page_number,
                        block.get("block_id"),
                    )
                    continue

                if page_number not in current_topic["pages"]:
                    current_topic["pages"].append(page_number)

                current_topic["tables"].append(
                    self._serialize_table(
                        page_number=page_number,
                        block=block,
                    )
                )

                self.logger.info(
                    "STEP_1 | table_attached | "
                    "topic=%s | page=%s | block=%s | rows=%s",
                    current_topic["topic_code"],
                    page_number,
                    block.get("block_id"),
                    table.get("row_count"),
                )

        return output

    def analyze(self) -> dict[str, Any]:
        self.logger.info("STEP_1 | risk_analysis | STARTED")

        data = self.load_input()

        pages = data.get("pages", [])

        enterprise_risks = self._extract_enterprise_risks(pages)

        material_topics = self._extract_material_topics(pages)

        result = {
            "document": {
                "document_id": data.get("document_id"),
                "document_hash": data.get("document_hash"),
                "source": data.get("source"),
            },
            "risk_analysis": {
                "enterprise_risks": enterprise_risks,
                "material_impacts_risks_and_opportunities": (
                    material_topics
                ),
            },
        }

        topic_count = len(material_topics["topics"])

        table_count = sum(
            len(topic["tables"])
            for topic in material_topics["topics"]
        )

        self.logger.info(
            "STEP_1 | risk_analysis | SUCCESS | "
            "topics=%s | material_tables=%s",
            topic_count,
            table_count,
        )

        return result

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
            "STEP_1 | output_write | SUCCESS | output=%s",
            output_path,
        )