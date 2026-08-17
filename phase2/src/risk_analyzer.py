from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class RiskAnalyzer:
    """
    Phase 2 - Step 1: Risk Analysis

    Responsibilities:
    - Read manually validated Phase-1 JSON
    - Identify relevant sections
    - Reconstruct section/topic/table hierarchy
    - Associate tables with topics using page layout / bounding boxes
    - Preserve page/block traceability
    - Produce a compact JSON for the generation stage

    No LLM is used here.
    """

    MATERIAL_SECTION = "Material impacts, risks, and opportunities"
    RISK_SECTION = "Risk management"

    MATERIAL_PAGES = {71, 72, 73, 74}
    ENTERPRISE_RISK_PAGES = {50, 51}

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

    # ------------------------------------------------------------------
    # INPUT
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # HEADING HELPERS
    # ------------------------------------------------------------------

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

            E1 Climate Change

        becomes:

            ("E1", "Climate Change")
        """
        parts = heading.split(maxsplit=1)

        topic_code = parts[0]
        topic_name = parts[1] if len(parts) > 1 else ""

        return topic_code, topic_name

    # ------------------------------------------------------------------
    # BOUNDING BOX HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _get_block_bbox(
        block: dict[str, Any],
    ) -> dict[str, float] | None:
        """
        Build a single bounding box for a block using provenance.

        Some blocks may contain multiple provenance entries, so this
        method creates a union bounding box.

        Expected coordinate system from Phase-1:
            BOTTOMLEFT

        Example:
            {
                "left": 51.02,
                "top": 505.35,
                "right": 287.61,
                "bottom": 490.24
            }
        """
        provenance = block.get("provenance", [])

        boxes = [
            item.get("bbox")
            for item in provenance
            if item.get("bbox")
        ]

        if not boxes:
            return None

        return {
            "left": min(box["left"] for box in boxes),
            "right": max(box["right"] for box in boxes),
            "top": max(box["top"] for box in boxes),
            "bottom": min(box["bottom"] for box in boxes),
        }

    @staticmethod
    def _horizontal_overlap_ratio(
        first_bbox: dict[str, float],
        second_bbox: dict[str, float],
    ) -> float:
        """
        Calculate horizontal overlap between two blocks.

        0.0 -> no overlap
        1.0 -> full overlap with respect to the smaller block
        """
        overlap_left = max(
            first_bbox["left"],
            second_bbox["left"],
        )

        overlap_right = min(
            first_bbox["right"],
            second_bbox["right"],
        )

        overlap_width = max(
            0.0,
            overlap_right - overlap_left,
        )

        first_width = max(
            first_bbox["right"] - first_bbox["left"],
            1.0,
        )

        second_width = max(
            second_bbox["right"] - second_bbox["left"],
            1.0,
        )

        smaller_width = min(
            first_width,
            second_width,
        )

        return overlap_width / smaller_width

    @staticmethod
    def _heading_is_above_table(
        heading_bbox: dict[str, float],
        table_bbox: dict[str, float],
    ) -> bool:
        """
        Determine whether heading is spatially above the table.

        Phase-1 uses BOTTOMLEFT coordinates, therefore a larger Y value
        means a block is higher on the page.

        Example:

            heading bottom = 490
            table top      = 472

        means heading is above the table.
        """
        return heading_bbox["bottom"] >= table_bbox["top"]

    @staticmethod
    def _vertical_distance(
        heading_bbox: dict[str, float],
        table_bbox: dict[str, float],
    ) -> float:
        """
        Distance between bottom of heading and top of table.

        Smaller value means heading is closer to the table.
        """
        return max(
            0.0,
            heading_bbox["bottom"] - table_bbox["top"],
        )

    # ------------------------------------------------------------------
    # TABLE SERIALIZATION
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_table(
        page_number: int,
        block: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Preserve relevant table content and traceability while
        removing unrelated parser-level metadata.
        """
        table = block.get("table", {})

        return {
            "page": page_number,
            "block_id": block.get("block_id"),
            "columns": table.get("columns", []),
            "rows": table.get("rows", []),
            "row_count": table.get("row_count", 0),
            "column_count": table.get("column_count", 0),
            "normalized": table.get("normalized", False),
            "provenance": block.get("provenance", []),
        }

    # ------------------------------------------------------------------
    # ENTERPRISE RISKS
    # ------------------------------------------------------------------

    def _extract_enterprise_risks(
        self,
        pages: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """
        Extract explicit enterprise principal-risk tables from the
        configured risk-management pages.
    
        The table is preserved structurally so downstream candidate
        extraction can interpret each declared risk column without
        relying on report-specific risk names.
        """
        result = {
            "section": self.RISK_SECTION,
            "subsection": "Main risks",
            "pages": [],
            "tables": [],
        }

        for page in pages:
            page_number = page.get("page_number")

            if page_number not in self.ENTERPRISE_RISK_PAGES:
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

    # ------------------------------------------------------------------
    # MATERIAL TOPIC COLLECTION
    # ------------------------------------------------------------------

    def _collect_topic_candidates(
        self,
        pages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Collect all E/S/G topic headings before table association.

        Important:
        We DO NOT associate tables while iterating through blocks.

        This avoids the issue:

            H1
            H2
            T1
            T2

        where sequential logic would incorrectly attach both T1/T2
        to H2.
        """
        topics: list[dict[str, Any]] = []

        for page in pages:
            page_number = page.get("page_number")

            if page_number not in self.MATERIAL_PAGES:
                continue

            for block in page.get("blocks", []):
                heading = self._get_heading_text(block)

                if not heading:
                    continue

                if heading in self.IGNORED_HEADINGS:
                    continue

                if not self._is_topic_heading(heading):
                    continue

                topic_code, topic_name = self._split_topic(
                    heading
                )

                bbox = self._get_block_bbox(block)

                topic = {
                    "topic_code": topic_code,
                    "topic_name": topic_name,
                    "page": page_number,
                    "block_id": block.get("block_id"),
                    "bbox": bbox,
                }

                topics.append(topic)

                self.logger.info(
                    "STEP_1 | topic_detected | "
                    "page=%s | code=%s | topic=%s | block=%s",
                    page_number,
                    topic_code,
                    topic_name,
                    block.get("block_id"),
                )

        return topics

    def _collect_table_candidates(
        self,
        pages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Collect all tables from material-risk pages.
        """
        tables: list[dict[str, Any]] = []

        for page in pages:
            page_number = page.get("page_number")

            if page_number not in self.MATERIAL_PAGES:
                continue

            for block in page.get("blocks", []):
                if block.get("type") != "table":
                    continue

                table = block.get("table")

                if not table:
                    continue

                tables.append(
                    {
                        "page": page_number,
                        "block": block,
                        "bbox": self._get_block_bbox(block),
                    }
                )

                self.logger.info(
                    "STEP_1 | table_detected | "
                    "page=%s | block=%s | rows=%s",
                    page_number,
                    block.get("block_id"),
                    table.get("row_count"),
                )

        return tables

    # ------------------------------------------------------------------
    # TABLE -> TOPIC MATCHING
    # ------------------------------------------------------------------

    def _find_parent_topic(
        self,
        table_candidate: dict[str, Any],
        topics: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """
        Find the most likely parent topic for a table.

        Matching priority:

        1. Same page
        2. Heading must be above the table
        3. Prefer nearest heading vertically
        4. Use horizontal overlap as secondary evidence

        This makes table association independent from the order
        in which blocks appear in the JSON.
        """
        table_page = table_candidate["page"]
        table_bbox = table_candidate["bbox"]

        if table_bbox is None:
            self.logger.warning(
                "STEP_1 | table_match | "
                "page=%s | block=%s | missing_bbox",
                table_page,
                table_candidate["block"].get("block_id"),
            )
            return self._fallback_parent_topic(
                table_page=table_page,
                topics=topics,
            )

        candidates: list[dict[str, Any]] = []

        for topic in topics:
            if topic["page"] != table_page:
                continue

            heading_bbox = topic.get("bbox")

            if heading_bbox is None:
                continue

            if not self._heading_is_above_table(
                heading_bbox,
                table_bbox,
            ):
                continue

            vertical_distance = self._vertical_distance(
                heading_bbox,
                table_bbox,
            )

            horizontal_overlap = (
                self._horizontal_overlap_ratio(
                    heading_bbox,
                    table_bbox,
                )
            )

            candidates.append(
                {
                    "topic": topic,
                    "vertical_distance": vertical_distance,
                    "horizontal_overlap": horizontal_overlap,
                }
            )

        if not candidates:
            return self._fallback_parent_topic(
                table_page=table_page,
                topics=topics,
            )

        # Primary criterion:
        # nearest valid heading above the table.
        #
        # Secondary criterion:
        # heading with better horizontal overlap.
        candidates.sort(
            key=lambda item: (
                item["vertical_distance"],
                -item["horizontal_overlap"],
            )
        )

        best_match = candidates[0]

        topic = best_match["topic"]

        self.logger.info(
            "STEP_1 | table_match | "
            "page=%s | table=%s | "
            "topic=%s | distance=%.2f | overlap=%.2f",
            table_page,
            table_candidate["block"].get("block_id"),
            topic["topic_code"],
            best_match["vertical_distance"],
            best_match["horizontal_overlap"],
        )

        return topic

    def _fallback_parent_topic(
        self,
        table_page: int,
        topics: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """
        Fallback for continuation tables or missing bounding boxes.

        Example:

            Page 71:
                E1 Climate Change
                Table 1

            Page 72:
                continuation Table 2

        If page 72 contains no new topic heading, Table 2 may still
        belong to E1.

        We therefore use the most recent topic from the current or
        preceding page as a controlled fallback.
        """
        preceding_topics = [
            topic
            for topic in topics
            if topic["page"] <= table_page
        ]

        if not preceding_topics:
            return None

        preceding_topics.sort(
            key=lambda topic: (
                topic["page"],
                (
                    topic["bbox"]["top"]
                    if topic.get("bbox")
                    else 0
                ),
            ),
            reverse=True,
        )

        topic = preceding_topics[0]

        self.logger.warning(
            "STEP_1 | table_match_fallback | "
            "table_page=%s | assigned_topic=%s | "
            "topic_page=%s",
            table_page,
            topic["topic_code"],
            topic["page"],
        )

        return topic

    # ------------------------------------------------------------------
    # HIERARCHY CONSTRUCTION
    # ------------------------------------------------------------------

    def _extract_material_topics(
        self,
        pages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Reconstruct:

        Material impacts, risks, and opportunities
        │
        ├── E1 Climate Change
        │      └── table(s)
        │
        ├── E4 Biodiversity and ecosystems
        │      └── table(s)
        │
        ├── E5 Circular economy and resource use
        │      └── table(s)
        │
        ├── S1 Own Workforce
        │      └── table(s)
        │
        └── ...
        """
        output = {
            "section": self.MATERIAL_SECTION,
            "topics": [],
        }

        # --------------------------------------------------------------
        # PASS 1
        # Collect headings and tables independently.
        # --------------------------------------------------------------

        topic_candidates = self._collect_topic_candidates(
            pages
        )

        table_candidates = self._collect_table_candidates(
            pages
        )

        # --------------------------------------------------------------
        # Build topic objects.
        # --------------------------------------------------------------

        topic_map: dict[
            tuple[str, str],
            dict[str, Any],
        ] = {}

        for topic in topic_candidates:
            topic_key = (
                topic["topic_code"],
                topic["topic_name"],
            )

            if topic_key not in topic_map:
                topic_map[topic_key] = {
                    "topic_code": topic["topic_code"],
                    "topic_name": topic["topic_name"],
                    "pages": [topic["page"]],
                    "source_headings": [
                        {
                            "page": topic["page"],
                            "block_id": topic["block_id"],
                        }
                    ],
                    "tables": [],
                }

                output["topics"].append(
                    topic_map[topic_key]
                )

            else:
                existing_topic = topic_map[topic_key]

                if (
                    topic["page"]
                    not in existing_topic["pages"]
                ):
                    existing_topic["pages"].append(
                        topic["page"]
                    )

                existing_topic[
                    "source_headings"
                ].append(
                    {
                        "page": topic["page"],
                        "block_id": topic["block_id"],
                    }
                )

        # --------------------------------------------------------------
        # PASS 2
        # Associate every table using layout geometry.
        # --------------------------------------------------------------

        for table_candidate in table_candidates:
            parent_topic = self._find_parent_topic(
                table_candidate=table_candidate,
                topics=topic_candidates,
            )

            if parent_topic is None:
                self.logger.warning(
                    "STEP_1 | orphan_table | "
                    "page=%s | block=%s",
                    table_candidate["page"],
                    table_candidate["block"].get(
                        "block_id"
                    ),
                )
                continue

            topic_key = (
                parent_topic["topic_code"],
                parent_topic["topic_name"],
            )

            topic_output = topic_map.get(topic_key)

            if topic_output is None:
                self.logger.warning(
                    "STEP_1 | topic_lookup_failed | "
                    "topic=%s",
                    parent_topic["topic_code"],
                )
                continue

            page_number = table_candidate["page"]

            if page_number not in topic_output["pages"]:
                topic_output["pages"].append(
                    page_number
                )

            serialized_table = self._serialize_table(
                page_number=page_number,
                block=table_candidate["block"],
            )

            topic_output["tables"].append(
                serialized_table
            )

            self.logger.info(
                "STEP_1 | table_attached | "
                "topic=%s | page=%s | block=%s | rows=%s",
                topic_output["topic_code"],
                page_number,
                table_candidate["block"].get(
                    "block_id"
                ),
                table_candidate["block"]
                .get("table", {})
                .get("row_count"),
            )

        # --------------------------------------------------------------
        # Final diagnostics.
        # --------------------------------------------------------------

        for topic in output["topics"]:
            if not topic["tables"]:
                self.logger.warning(
                    "STEP_1 | topic_without_table | "
                    "topic=%s | pages=%s",
                    topic["topic_code"],
                    topic["pages"],
                )

            topic["pages"] = sorted(
                set(topic["pages"])
            )

        return output

    # ------------------------------------------------------------------
    # MAIN ANALYSIS
    # ------------------------------------------------------------------

    def analyze(self) -> dict[str, Any]:
        self.logger.info(
            "STEP_1 | risk_analysis | STARTED"
        )

        data = self.load_input()

        pages = data.get("pages", [])

        enterprise_risks = (
            self._extract_enterprise_risks(
                pages
            )
        )

        material_topics = (
            self._extract_material_topics(
                pages
            )
        )

        result = {
            "document": {
                "document_id": data.get(
                    "document_id"
                ),
                "document_hash": data.get(
                    "document_hash"
                ),
                "source": data.get("source"),
            },
            "risk_analysis": {
                "enterprise_risks": (
                    enterprise_risks
                ),
                "material_impacts_risks_and_opportunities": (
                    material_topics
                ),
            },
        }

        topic_count = len(
            material_topics["topics"]
        )

        table_count = sum(
            len(topic["tables"])
            for topic in material_topics["topics"]
        )

        empty_topic_count = sum(
            1
            for topic in material_topics["topics"]
            if not topic["tables"]
        )

        self.logger.info(
            "STEP_1 | risk_analysis | SUCCESS | "
            "topics=%s | material_tables=%s | "
            "topics_without_tables=%s",
            topic_count,
            table_count,
            empty_topic_count,
        )

        return result

    # ------------------------------------------------------------------
    # SAVE OUTPUT
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
            "STEP_1 | output_write | SUCCESS | "
            "output=%s",
            output_path,
        )