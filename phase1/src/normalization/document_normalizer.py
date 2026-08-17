from __future__ import annotations

from typing import Any

from models import (
    BlockType,
    BoundingBox,
    CanonicalDocument,
    ContentBlock,
    DocumentSource,
    PageData,
    Provenance,
    TableData,
)

from normalization.table_normalizer import (
    TableNormalizer,
)

from normalization.text_normalizer import (
    TextNormalizer,
)


class DocumentNormalizer:
    """
    Convert raw parser output into the application's
    parser-independent canonical document model.
    """

    def __init__(self) -> None:

        self.text_normalizer = (
            TextNormalizer()
        )

        self.table_normalizer = (
            TableNormalizer(
                text_normalizer=(
                    self.text_normalizer
                )
            )
        )

    def normalize(
        self,
        raw_document: dict[str, Any],
        ) -> CanonicalDocument:

        table_lookup = (
            self._build_table_lookup(
                raw_document.get(
                    "tables",
                    [],
                )
            )
        )

        pages: list[PageData] = []

        for raw_page in raw_document.get(
            "pages",
            [],
        ):

            page = self._normalize_page(
                raw_page=raw_page,
                table_lookup=table_lookup,
            )

            pages.append(page)

        source = raw_document.get(
            "source",
            {},
        )

        return CanonicalDocument(
            document_id=raw_document.get(
                "document_id",
                "",
            ),
            document_hash=raw_document.get(
                "document_hash",
                "",
            ),
            source=DocumentSource(
                file_name=source.get(
                    "file_name",
                    "",
                ),
                file_type=source.get(
                    "file_type",
                    "",
                ),
                file_size_bytes=source.get(
                    "file_size_bytes"
                ),
                source_path=source.get(
                    "source_path"
                ),
            ),
            pages=pages,
            metadata=raw_document.get(
                "document_metadata",
                {},
            ),
            parser=self._build_parser_metadata(
                raw_document
            ),
            normalization={
                "applied": True,
                "version": "1.0.0",
                "operations": [
                    "canonical_schema_conversion",
                    "text_cleanup",
                    "decorative_visual_filtering",
                    "table_header_reconstruction",
                ],
            },
            warnings=raw_document.get(
                "warnings",
                [],
            ),
        )

    
    def _normalize_page(
        self,
        raw_page: dict[str, Any],
        table_lookup: dict[str, dict[str, Any]],
    ) -> PageData:

        blocks: list[ContentBlock] = []

        raw_content = raw_page.get(
            "content",
            [],
        )

        for index, raw_block in enumerate(
            raw_content,
            start=1,
        ):

            block = self._convert_block(
                raw_block=raw_block,
                page_number=raw_page.get(
                    "page_number",
                    0,
                ),
                fallback_id=(
                    f"block-{index}"
                ),
                table_lookup=table_lookup,
            )

            if self._should_keep_block(
                block
            ):
                blocks.append(block)

        for index, block in enumerate(
            blocks
        ):

            if block.type == BlockType.TABLE:

                blocks[index] = (
                    self.table_normalizer
                    .normalize(
                        table_block=block,
                        page_blocks=blocks,
                    )
                )

        return PageData(
            page_number=raw_page.get(
                "page_number",
                0,
            ),
            page_type=raw_page.get(
                "page_type"
            ),
            blocks=blocks,
            metadata={
                "original_contains": (
                    raw_page.get(
                        "contains",
                        {},
                    )
                ),
                "ocr": raw_page.get(
                    "ocr",
                    {},
                ),
            },
        )

    def _convert_block(
        self,
        raw_block: dict[str, Any],
        page_number: int,
        fallback_id: str,
        table_lookup: dict[str, dict[str, Any]],
    ) -> ContentBlock:

        raw_type = raw_block.get(
            "type",
            "unknown",
        )

        block_type = self._map_block_type(
            raw_type
        )

        provenance = (
            self._convert_provenance(
                raw_block.get(
                    "provenance",
                    [],
                )
            )
        )

        table_data = None

        if block_type == BlockType.TABLE:
        
            block_id = raw_block.get(
                "block_id",
                fallback_id,
            )

            raw_table = (
                table_lookup.get(
                    block_id,
                    raw_block,
                )
            )

            rows = raw_table.get(
                "rows",
                [],
            )

            columns = raw_table.get(
                "columns",
                [],
            )

            table_data = TableData(
                columns=list(columns),
                rows=[
                    list(row)
                    for row in rows
                ],
                row_count=raw_table.get(
                    "row_count",
                    len(rows),
                ),
                column_count=raw_table.get(
                    "column_count",
                    len(columns),
                ),
            )

            # Some existing parser outputs
            # may store row/column data only
            # in the global table collection.
            #
            # This block is still preserved
            # even when table_data is empty.

        classification = (
            self._extract_classification(
                raw_block
            )
        )

        confidence = (
            self._extract_confidence(
                raw_block
            )
        )

        return ContentBlock(
            block_id=raw_block.get(
                "block_id",
                fallback_id,
            ),
            page_number=page_number,
            type=block_type,
            text=self.text_normalizer.normalize(
                raw_block.get(
                    "text",
                    "",
                )
            ),
            provenance=provenance,
            table=table_data,
            extraction_method=(
                raw_block.get(
                    "extraction_method"
                )
            ),
            classification=classification,
            confidence=confidence,
            metadata={
                "original_type": raw_type
            },
        )

    def _convert_provenance(
        self,
        raw_provenance: list[dict[str, Any]],
    ) -> list[Provenance]:

        result: list[Provenance] = []

        for prov in raw_provenance:

            bbox_data = prov.get(
                "bbox"
            )

            bbox = None

            if bbox_data:

                bbox = BoundingBox(
                    left=bbox_data.get(
                        "l",
                        0.0,
                    ),
                    top=bbox_data.get(
                        "t",
                        0.0,
                    ),
                    right=bbox_data.get(
                        "r",
                        0.0,
                    ),
                    bottom=bbox_data.get(
                        "b",
                        0.0,
                    ),
                    coordinate_origin=(
                        bbox_data.get(
                            "coord_origin",
                            "BOTTOMLEFT",
                        )
                    ),
                )

            character_span = prov.get(
                "character_span",
                [],
            )

            character_start = None
            character_end = None

            if len(character_span) == 2:
                character_start = (
                    character_span[0]
                )
                character_end = (
                    character_span[1]
                )

            result.append(
                Provenance(
                    page_number=prov.get(
                        "page_number",
                        0,
                    ),
                    bbox=bbox,
                    character_start=(
                        character_start
                    ),
                    character_end=(
                        character_end
                    ),
                )
            )

        return result

    def _map_block_type(
        self,
        raw_type: str,
    ) -> BlockType:

        mapping = {
            "text": BlockType.TEXT,
            "section_header": (
                BlockType.HEADING
            ),
            "title": BlockType.HEADING,

            "table": BlockType.TABLE,

            "chart": BlockType.CHART,
            "bar_chart": BlockType.CHART,
            "line_chart": BlockType.CHART,
            "pie_chart": BlockType.CHART,
            "scatter_plot": BlockType.CHART,
            "box_plot": BlockType.CHART,

            "flow_chart": BlockType.DIAGRAM,
            "diagram": BlockType.DIAGRAM,

            "picture": BlockType.IMAGE,
            "photograph": BlockType.IMAGE,
            "photo": BlockType.IMAGE,
            "full_page_image": (
                BlockType.IMAGE
            ),
        }

        return mapping.get(
            raw_type,
            BlockType.UNKNOWN,
        )

    def _should_keep_block(
        self,
        block: ContentBlock,
    ) -> bool:

        # Text/heading/table always retained.
        if block.type in {
            BlockType.TEXT,
            BlockType.HEADING,
            BlockType.TABLE,
            BlockType.CHART,
            BlockType.DIAGRAM,
        }:
            return True

        # Remove obvious decorative icons.
        if (
            block.classification
            == "icon"
        ):
            return False

        # Logos are generally irrelevant
        # for risk extraction.
        if (
            block.classification
            == "logo"
        ):
            return False

        return True

    @staticmethod
    def _extract_classification(
        raw_block: dict[str, Any],
    ) -> str | None:

        classification = (
            raw_block.get(
                "classification"
            )
        )

        if isinstance(
            classification,
            dict,
        ):
            return classification.get(
                "primary_label"
            )

        if isinstance(
            classification,
            str,
        ):
            return classification

        return None

    @staticmethod
    def _extract_confidence(
        raw_block: dict[str, Any],
    ) -> float | None:

        classification = (
            raw_block.get(
                "classification"
            )
        )

        if not isinstance(
            classification,
            dict,
        ):
            return None

        scores = classification.get(
            "confidence_scores",
            [],
        )

        if not scores:
            return None

        try:
            return float(scores[0])

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _build_table_lookup(
        tables: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
    
        lookup = {}
    
        for table in tables:
        
            table_id = table.get(
                "table_id"
            )
    
            if table_id:
                lookup[table_id] = table
    
        return lookup
    @staticmethod
    def _build_parser_metadata(
        raw_document: dict[str, Any],
    ) -> dict[str, Any]:

        processing = raw_document.get(
            "processing",
            {},
        )

        return {
            "name": processing.get(
                "parser_name"
            ),
            "version": processing.get(
                "parser_version"
            ),
            "strategy": processing.get(
                "strategy"
            ),
        }