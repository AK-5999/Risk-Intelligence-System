from __future__ import annotations

import hashlib
import json
import os
import uuid

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Keep local Windows execution simple.
os.environ.setdefault("TORCHINDUCTOR_DISABLE", "1")
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    OcrMode,
    PdfPipelineOptions,
    RapidOcrOptions,
)

from docling.datamodel.accelerator_options import (
    AcceleratorOptions,
    AcceleratorDevice,
)

from docling.document_converter import (
    DocumentConverter,
    PdfFormatOption,
)


from parsing.base_parser import DocumentParser


class PDFParser(DocumentParser):
    """
    Adaptive two-pass PDF parser using Docling.

    Pass 1:
    - OCR disabled
    - Complete document layout analysis
    - Native text extraction
    - Table extraction
    - Picture detection
    - Chart and diagram candidate identification
    - OCR candidate-page identification

    Pass 2:
    - OCR enabled only for candidate pages
    - OCR output merged into the original page result

    Extraction rules:
    - Normal text -> plain text
    - Table -> Markdown
    - Picture/chart/diagram -> Docling annotations
    - Scanned/image-based page -> OCR text
    """

    PARSER_NAME = "docling-adaptive-pdf-parser"
    PARSER_VERSION = "3.0.0"

    TEXT_LABELS = {
        "text",
        "title",
        "section_header",
        "list_item",
        "caption",
        "footnote",
        "page_header",
        "page_footer",
        "formula",
        "code",
    }

    CHART_TERMS = {
        "chart",
        "bar_chart",
        "bar chart",
        "line_chart",
        "line chart",
        "pie_chart",
        "pie chart",
        "scatter",
        "histogram",
        "plot",
        "graph",
    }

    DIAGRAM_TERMS = {
        "diagram",
        "flowchart",
        "flow chart",
        "architecture",
        "schematic",
        "process diagram",
        "technical drawing",
    }

    def __init__(
        self,
        enable_table_structure: bool = True,
        enable_picture_classification: bool = True,
        enable_chart_extraction: bool = True,
        generate_picture_images: bool = True,
        images_scale: float = 2.0,
        minimum_native_text_characters: int = 20,
    ) -> None:
        self.enable_table_structure = enable_table_structure
        self.enable_picture_classification = (
            enable_picture_classification
        )
        self.enable_chart_extraction = (
            enable_chart_extraction
        )
        self.generate_picture_images = (
            generate_picture_images
        )
        self.images_scale = images_scale
        self.minimum_native_text_characters = (
            minimum_native_text_characters
        )

        self.detection_converter = (
            self._build_detection_converter()
        )

        self.ocr_converter = self._build_ocr_converter()

    def _build_detection_converter(
        self,
    ) -> DocumentConverter:
        """
        Build Pass-1 converter.

        OCR is disabled. This pass performs layout and native-content
        detection across the complete PDF.
        """

        options = PdfPipelineOptions()
        options.accelerator_options = AcceleratorOptions(
            device=AcceleratorDevice.CUDA,
            num_threads=2,
        )

        options.do_ocr = False
        options.do_table_structure = (
            self.enable_table_structure
        )
        options.generate_picture_images = (
            self.generate_picture_images
        )
        options.images_scale = self.images_scale

        # These options depend on the installed Docling version.
        # hasattr keeps the POC compatible with versions where one
        # enrichment option may not yet be available.
        if hasattr(options, "do_picture_classification"):
            options.do_picture_classification = (
                self.enable_picture_classification
            )

        if hasattr(options, "do_chart_extraction"):
            options.do_chart_extraction = (
                self.enable_chart_extraction
            )

        return DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=options
                )
            },
        )

    def _build_ocr_converter(
        self,
    ) -> DocumentConverter:
        """
        Build Pass-2 OCR converter.

        This converter is called only for pages identified as OCR
        candidates during Pass 1.
        """

        options = PdfPipelineOptions()

        options.accelerator_options = AcceleratorOptions(
            device=AcceleratorDevice.CUDA,
            num_threads=2,
        )
        options.do_ocr = True
        options.do_table_structure = (
            self.enable_table_structure
        )

        # Full-page OCR is used because Pass 2 only receives pages
        # already identified as scanned/image-based candidates.
        options.ocr_options = RapidOcrOptions(
            lang=["english"],
            mode=OcrMode.FULL_PAGE,
        )

        options.generate_picture_images = False

        if hasattr(options, "do_picture_classification"):
            options.do_picture_classification = False

        if hasattr(options, "do_chart_extraction"):
            options.do_chart_extraction = False

        return DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=options
                )
            },
        )

    def can_parse(self, file_path: Path) -> bool:
        """Return True when the supplied file is a valid PDF path."""

        return (
            file_path.exists()
            and file_path.is_file()
            and file_path.suffix.lower() == ".pdf"
        )

    def inspect(self, file_path: Path) -> dict[str, Any]:
        """Return lightweight file-level metadata."""

        self._validate_file(file_path)

        return {
            "file_name": file_path.name,
            "file_type": "pdf",
            "file_size_bytes": file_path.stat().st_size,
            "source_path": str(file_path.resolve()),
        }

    def calculate_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 from the actual file bytes."""

        self._validate_file(file_path)

        sha256 = hashlib.sha256()

        with file_path.open("rb") as pdf_file:
            while True:
                chunk = pdf_file.read(1024 * 1024)

                if not chunk:
                    break

                sha256.update(chunk)

        return sha256.hexdigest()

    def parse(
        self,
        file_path: Path,
        document_hash: str | None = None,
        page_range: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        """
        Run adaptive two-pass extraction.

        Pass 1 runs without OCR.
        Pass 2 runs OCR only on identified candidate pages.
        """

        self._validate_file(file_path)
        self._validate_page_range(page_range)

        started_at = self._timestamp()
        document_id = str(uuid.uuid4())

        if document_hash is None:
            document_hash = self.calculate_hash(file_path)

        try:
            # -------------------------------------------------
            # PASS 1: DETECTION WITHOUT OCR
            # -------------------------------------------------

            detection_result = self._convert(
                converter=self.detection_converter,
                file_path=file_path,
                page_range=page_range,
            )

            document = detection_result.document

            blocks = self._extract_blocks(document)
            tables = self._extract_tables(document)
            pictures = self._extract_pictures(document)

            pages = self._build_detection_pages(
                document=document,
                blocks=blocks,
                tables=tables,
                pictures=pictures,
            )

            ocr_candidate_pages = [
                page["page_number"]
                for page in pages
                if page["ocr"]["required"]
            ]

            # -------------------------------------------------
            # PASS 2: SELECTIVE OCR
            # -------------------------------------------------

            ocr_results = self._run_selective_ocr(
                file_path=file_path,
                candidate_pages=ocr_candidate_pages,
            )

            self._merge_ocr_results(
                pages=pages,
                ocr_results=ocr_results,
            )

            # -------------------------------------------------
            # FINAL CONTENT ASSEMBLY
            # -------------------------------------------------

            self._build_page_content(
                pages=pages,
                blocks=blocks,
                tables=tables,
                pictures=pictures,
            )

            label_counts = Counter(
                block["type"]
                for block in blocks
            )

            page_type_counts = Counter(
                page["page_type"]
                for page in pages
            )

            pages_with_text = sum(
                1
                for page in pages
                if page["contains"]["text"]
            )

            pages_with_tables = sum(
                1
                for page in pages
                if page["contains"]["table"]
            )

            pages_with_pictures = sum(
                1
                for page in pages
                if page["contains"]["picture"]
            )

            ocr_pages_processed = sum(
                1
                for page in pages
                if page["ocr"]["applied"]
            )

            empty_pages = sum(
                1
                for page in pages
                if page["page_type"]
                == "empty_or_unresolved"
            )

            total_pages = len(pages)

            warnings = self._generate_document_warnings(
                pages=pages,
                tables=tables,
                pictures=pictures,
            )

            quality_score = self._quality_score(
                total_pages=total_pages,
                empty_pages=empty_pages,
            )

            status = (
                "completed_with_warnings"
                if warnings
                else "completed"
            )

            return {
                "document_id": document_id,
                "document_hash": document_hash,
                "source": {
                    "file_name": file_path.name,
                    "file_type": "pdf",
                    "file_size_bytes": (
                        file_path.stat().st_size
                    ),
                    "source_path": str(
                        file_path.resolve()
                    ),
                },
                "document_metadata": {
                    "page_count": total_pages,
                    "processed_page_range": (
                        list(page_range)
                        if page_range
                        else None
                    ),
                    "title": self._document_name(
                        document
                    ),
                },
                "processing": {
                    "parser_name": self.PARSER_NAME,
                    "parser_version": self.PARSER_VERSION,
                    "processing_started_at": started_at,
                    "processing_completed_at": (
                        self._timestamp()
                    ),
                    "status": status,
                    "strategy": "adaptive_two_pass",
                    "pass_1": {
                        "purpose": (
                            "Layout and native-content "
                            "detection"
                        ),
                        "ocr_enabled": False,
                    },
                    "pass_2": {
                        "purpose": (
                            "OCR only on candidate pages"
                        ),
                        "ocr_enabled": True,
                        "candidate_pages": (
                            ocr_candidate_pages
                        ),
                        "processed_pages": [
                            page_number
                            for page_number, value
                            in ocr_results.items()
                            if value.get("success")
                        ],
                    },
                },
                "content_summary": {
                    "total_blocks": len(blocks),
                    "total_tables": len(tables),
                    "total_pictures": len(pictures),
                    "label_counts": dict(label_counts),
                    "page_type_counts": dict(
                        page_type_counts
                    ),
                    "ocr_required_page_count": len(
                        ocr_candidate_pages
                    ),
                    "ocr_required_pages": (
                        ocr_candidate_pages
                    ),
                },
                "pages": pages,
                "blocks": blocks,
                "tables": tables,
                "pictures": pictures,
                "markdown": (
                    document.export_to_markdown()
                ),
                "quality": {
                    "pages_processed": total_pages,
                    "pages_with_text": pages_with_text,
                    "pages_with_tables": pages_with_tables,
                    "pages_with_pictures": (
                        pages_with_pictures
                    ),
                    "pages_requiring_ocr": len(
                        ocr_candidate_pages
                    ),
                    "ocr_pages_processed": (
                        ocr_pages_processed
                    ),
                    "empty_pages": empty_pages,
                    "failed_pages": 0,
                    "overall_quality_score": (
                        quality_score
                    ),
                },
                "warnings": warnings,
                "errors": [],
            }

        except Exception as error:
            return self._failed_result(
                file_path=file_path,
                document_id=document_id,
                document_hash=document_hash,
                started_at=started_at,
                page_range=page_range,
                error=error,
            )

    def _convert(
        self,
        converter: DocumentConverter,
        file_path: Path,
        page_range: tuple[int, int] | None,
    ) -> Any:
        """Run a Docling conversion."""

        if page_range is None:
            return converter.convert(
                source=file_path,
            )

        return converter.convert(
            source=file_path,
            page_range=page_range,
        )

    def _extract_blocks(
        self,
        document: Any,
    ) -> list[dict[str, Any]]:
        """Extract document items in reading order."""

        blocks: list[dict[str, Any]] = []

        for sequence, item_data in enumerate(
            document.iterate_items(),
            start=1,
        ):
            item, hierarchy_level = item_data

            label = self._item_label(item)
            text = self._item_text(item)
            provenance = self._provenance(item)

            page_numbers = sorted(
                {
                    entry["page_number"]
                    for entry in provenance
                    if entry["page_number"] is not None
                }
            )

            blocks.append(
                {
                    "block_id": self._item_reference(
                        item,
                        fallback=f"block-{sequence}",
                    ),
                    "sequence_number": sequence,
                    "hierarchy_level": hierarchy_level,
                    "type": label,
                    "text": text,
                    "character_count": len(text),
                    "word_count": (
                        len(text.split())
                        if text
                        else 0
                    ),
                    "page_numbers": page_numbers,
                    "provenance": provenance,
                    "annotations": self._annotations(
                        item
                    ),
                }
            )

        return blocks

    def _extract_tables(
        self,
        document: Any,
    ) -> list[dict[str, Any]]:
        """
        Extract table rows, columns and Markdown representation.
        """

        tables: list[dict[str, Any]] = []

        for number, table in enumerate(
            getattr(document, "tables", []),
            start=1,
        ):
            columns: list[str] = []
            rows: list[list[str]] = []
            markdown = ""
            warning: str | None = None

            try:
                dataframe = table.export_to_dataframe(
                    doc=document
                )

                columns = [
                    self._safe_string(column)
                    for column in dataframe.columns
                ]

                rows = [
                    [
                        self._safe_string(cell)
                        for cell in row
                    ]
                    for row in dataframe.itertuples(
                        index=False,
                        name=None,
                    )
                ]

                markdown = dataframe.to_markdown(
                    index=False
                )

            except Exception as error:
                warning = (
                    "Table detected but Markdown export "
                    "failed: "
                    f"{type(error).__name__}: {error}"
                )

            provenance = self._provenance(table)

            page_numbers = sorted(
                {
                    entry["page_number"]
                    for entry in provenance
                    if entry["page_number"] is not None
                }
            )

            tables.append(
                {
                    "table_id": self._item_reference(
                        table,
                        fallback=f"table-{number}",
                    ),
                    "table_number": number,
                    "page_numbers": page_numbers,
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "column_count": len(columns),
                    "markdown": markdown,
                    "provenance": provenance,
                    "warning": warning,
                }
            )

        return tables

    def _extract_pictures(
        self,
        document: Any,
    ) -> list[dict[str, Any]]:
        """Extract pictures and available Docling annotations."""

        pictures: list[dict[str, Any]] = []

        for number, picture in enumerate(
            getattr(document, "pictures", []),
            start=1,
        ):
            provenance = self._provenance(picture)
            annotations = self._annotations(picture)

            classification = (
                self._picture_classification(
                    annotations
                )
            )

            page_numbers = sorted(
                {
                    entry["page_number"]
                    for entry in provenance
                    if entry["page_number"] is not None
                }
            )

            pictures.append(
                {
                    "picture_id": self._item_reference(
                        picture,
                        fallback=f"picture-{number}",
                    ),
                    "picture_number": number,
                    "page_numbers": page_numbers,
                    "classification": classification,
                    "provenance": provenance,
                    "annotations": annotations,
                }
            )

        return pictures

    def _build_detection_pages(
        self,
        document: Any,
        blocks: list[dict[str, Any]],
        tables: list[dict[str, Any]],
        pictures: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build Pass-1 page classification."""

        page_numbers = self._page_numbers(
            document=document,
            blocks=blocks,
            tables=tables,
            pictures=pictures,
        )

        pages: list[dict[str, Any]] = []

        for page_number in sorted(page_numbers):
            page_blocks = [
                block
                for block in blocks
                if page_number in block["page_numbers"]
            ]

            page_tables = [
                table
                for table in tables
                if page_number in table["page_numbers"]
            ]

            page_pictures = [
                picture
                for picture in pictures
                if page_number
                in picture["page_numbers"]
            ]

            text_blocks = [
                block
                for block in page_blocks
                if (
                    block["type"] in self.TEXT_LABELS
                    and block["text"]
                )
            ]

            native_text = "\n".join(
                block["text"]
                for block in text_blocks
            )

            chart_pictures = [
                picture
                for picture in page_pictures
                if self._matches_terms(
                    picture["classification"],
                    self.CHART_TERMS,
                )
            ]

            diagram_pictures = [
                picture
                for picture in page_pictures
                if self._matches_terms(
                    picture["classification"],
                    self.DIAGRAM_TERMS,
                )
            ]

            contains_text = bool(native_text.strip())
            contains_table = bool(page_tables)
            contains_picture = bool(page_pictures)
            contains_chart = bool(chart_pictures)
            contains_diagram = bool(
                diagram_pictures
            )

            ocr_required, ocr_reason = (
                self._ocr_decision(
                    text_character_count=len(
                        native_text
                    ),
                    contains_picture=contains_picture,
                    total_blocks=len(page_blocks),
                )
            )

            page_type = self._page_type(
                contains_text=contains_text,
                contains_table=contains_table,
                contains_picture=contains_picture,
                contains_chart=contains_chart,
                contains_diagram=contains_diagram,
                ocr_required=ocr_required,
            )

            pages.append(
                {
                    "page_number": page_number,
                    "page_type": page_type,
                    "contains": {
                        "text": contains_text,
                        "table": contains_table,
                        "picture": contains_picture,
                        "chart": contains_chart,
                        "diagram": contains_diagram,
                    },
                    "native_text": native_text,
                    "ocr_text": "",
                    "final_text": native_text,
                    "ocr": {
                        "required": ocr_required,
                        "reason": ocr_reason,
                        "applied": False,
                        "success": False,
                        "error": None,
                    },
                    "content": [],
                    "block_ids": [
                        block["block_id"]
                        for block in page_blocks
                    ],
                    "table_ids": [
                        table["table_id"]
                        for table in page_tables
                    ],
                    "picture_ids": [
                        picture["picture_id"]
                        for picture in page_pictures
                    ],
                    "metadata": {
                        "block_count": len(page_blocks),
                        "text_block_count": len(
                            text_blocks
                        ),
                        "table_count": len(
                            page_tables
                        ),
                        "picture_count": len(
                            page_pictures
                        ),
                        "chart_count": len(
                            chart_pictures
                        ),
                        "diagram_count": len(
                            diagram_pictures
                        ),
                    },
                    "warnings": [],
                }
            )

        return pages

    def _run_selective_ocr(
        self,
        file_path: Path,
        candidate_pages: list[int],
    ) -> dict[int, dict[str, Any]]:
        """
        Run OCR only for candidate pages.

        Each candidate page is converted separately so failure on one
        page does not stop OCR for the remaining pages.
        """

        results: dict[int, dict[str, Any]] = {}

        for page_number in candidate_pages:
            try:
                conversion = self.ocr_converter.convert(
                    source=file_path,
                    page_range=(
                        page_number,
                        page_number,
                    ),
                )

                ocr_document = conversion.document

                text_parts: list[str] = []

                for item, _ in ocr_document.iterate_items():
                    text = self._item_text(item)

                    if text:
                        text_parts.append(text)

                ocr_text = "\n".join(text_parts).strip()

                results[page_number] = {
                    "success": bool(ocr_text),
                    "text": ocr_text,
                    "error": (
                        None
                        if ocr_text
                        else "OCR returned no text."
                    ),
                }

            except Exception as error:
                results[page_number] = {
                    "success": False,
                    "text": "",
                    "error": (
                        f"{type(error).__name__}: "
                        f"{error}"
                    ),
                }

        return results

    @staticmethod
    def _merge_ocr_results(
        pages: list[dict[str, Any]],
        ocr_results: dict[int, dict[str, Any]],
    ) -> None:
        """Merge selective OCR output into page records."""

        for page in pages:
            page_number = page["page_number"]

            if page_number not in ocr_results:
                continue

            result = ocr_results[page_number]

            page["ocr"]["applied"] = True
            page["ocr"]["success"] = result["success"]
            page["ocr"]["error"] = result["error"]
            page["ocr_text"] = result["text"]

            if result["success"]:
                page["final_text"] = result["text"]
                page["contains"]["text"] = True

                if page["page_type"] in {
                    "scanned_or_image_based",
                    "empty_or_unresolved",
                }:
                    page["page_type"] = (
                        "ocr_text"
                    )

            else:
                page["warnings"].append(
                    "OCR was applied but no text "
                    "was extracted."
                )

    @staticmethod
    def _build_page_content(
        pages: list[dict[str, Any]],
        blocks: list[dict[str, Any]],
        tables: list[dict[str, Any]],
        pictures: list[dict[str, Any]],
    ) -> None:
        """
        Build type-specific page content.

        Text is plain text.
        Tables are Markdown.
        Figures use Docling classification and annotations.
        """

        block_map = {
            block["block_id"]: block
            for block in blocks
        }

        table_map = {
            table["table_id"]: table
            for table in tables
        }

        picture_map = {
            picture["picture_id"]: picture
            for picture in pictures
        }

        for page in pages:
            content: list[dict[str, Any]] = []

            if page["ocr"]["applied"]:
                content.append(
                    {
                        "type": "ocr_text",
                        "text": page["ocr_text"],
                        "extraction_method": "ocr",
                    }
                )
            else:
                for block_id in page["block_ids"]:
                    block = block_map.get(block_id)

                    if not block:
                        continue

                    if (
                        block["type"]
                        not in PDFParser.TEXT_LABELS
                    ):
                        continue

                    if not block["text"]:
                        continue

                    content.append(
                        {
                            "type": block["type"],
                            "text": block["text"],
                            "extraction_method": (
                                "native_pdf_text"
                            ),
                            "provenance": block[
                                "provenance"
                            ],
                        }
                    )

            for table_id in page["table_ids"]:
                table = table_map.get(table_id)

                if not table:
                    continue

                content.append(
                    {
                        "type": "table",
                        "markdown": table["markdown"],
                        "columns": table["columns"],
                        "rows": table["rows"],
                        "extraction_method": (
                            "docling_table_structure"
                        ),
                        "provenance": table[
                            "provenance"
                        ],
                        "warning": table["warning"],
                    }
                )

            for picture_id in page["picture_ids"]:
                picture = picture_map.get(
                    picture_id
                )

                if not picture:
                    continue

                primary_label = picture[
                    "classification"
                ].get("primary_label")

                picture_type = (
                    primary_label
                    if primary_label
                    else "picture"
                )

                content.append(
                    {
                        "type": picture_type,
                        "classification": picture[
                            "classification"
                        ],
                        "annotations": picture[
                            "annotations"
                        ],
                        "extraction_method": (
                            "docling_picture_analysis"
                        ),
                        "provenance": picture[
                            "provenance"
                        ],
                    }
                )

            page["content"] = content

    def _ocr_decision(
        self,
        text_character_count: int,
        contains_picture: bool,
        total_blocks: int,
    ) -> tuple[bool, str | None]:
        """
        Decide whether OCR is required.

        This is a POC heuristic.
        """

        if total_blocks == 0:
            return (
                True,
                "No layout or native-text blocks "
                "were detected.",
            )

        if text_character_count == 0:
            return (
                True,
                "No native text was extracted.",
            )

        if (
            contains_picture
            and text_character_count
            < self.minimum_native_text_characters
        ):
            return (
                True,
                "Very little native text was found "
                "on a picture-heavy page.",
            )

        return False, None

    @staticmethod
    def _page_type(
        contains_text: bool,
        contains_table: bool,
        contains_picture: bool,
        contains_chart: bool,
        contains_diagram: bool,
        ocr_required: bool,
    ) -> str:
        """Return a high-level page type."""

        if ocr_required and not contains_text:
            return "scanned_or_image_based"

        major_types = sum(
            [
                contains_text,
                contains_table,
                contains_picture,
            ]
        )

        if major_types > 1:
            return "mixed"

        if contains_chart:
            return "chart"

        if contains_diagram:
            return "diagram"

        if contains_table:
            return "table"

        if contains_picture:
            return "picture"

        if contains_text:
            return "text"

        return "empty_or_unresolved"

    def _picture_classification(
        self,
        annotations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Extract labels from Docling annotations."""

        labels: list[str] = []
        scores: list[float] = []

        for annotation in annotations:
            serialized = json.dumps(
                annotation,
                ensure_ascii=False,
                default=str,
            ).lower()

            self._collect_labels(
                value=annotation,
                labels=labels,
                scores=scores,
            )

            if "chart" in serialized:
                labels.append("chart")

            if "diagram" in serialized:
                labels.append("diagram")

            if "photo" in serialized:
                labels.append("photo")

            if "logo" in serialized:
                labels.append("logo")

        unique_labels = list(
            dict.fromkeys(
                label.strip().lower()
                for label in labels
                if label.strip()
            )
        )

        return {
            "primary_label": (
                unique_labels[0]
                if unique_labels
                else None
            ),
            "labels": unique_labels,
            "confidence_scores": scores,
        }

    def _collect_labels(
        self,
        value: Any,
        labels: list[str],
        scores: list[float],
    ) -> None:
        """Recursively collect classification labels."""

        if isinstance(value, dict):
            for key, child in value.items():
                normalized_key = str(key).lower()

                if normalized_key in {
                    "label",
                    "class_name",
                    "category",
                    "prediction",
                } and isinstance(child, str):
                    labels.append(child)

                elif normalized_key in {
                    "score",
                    "confidence",
                    "confidence_score",
                } and isinstance(
                    child,
                    (int, float),
                ):
                    scores.append(float(child))

                else:
                    self._collect_labels(
                        child,
                        labels,
                        scores,
                    )

        elif isinstance(value, list):
            for child in value:
                self._collect_labels(
                    child,
                    labels,
                    scores,
                )

    @staticmethod
    def _matches_terms(
        classification: dict[str, Any],
        terms: set[str],
    ) -> bool:
        """Check picture labels against chart/diagram terms."""

        labels = classification.get(
            "labels",
            [],
        )

        combined = " ".join(
            str(label).lower()
            for label in labels
        )

        return any(
            term in combined
            for term in terms
        )

    def _page_numbers(
        self,
        document: Any,
        blocks: list[dict[str, Any]],
        tables: list[dict[str, Any]],
        pictures: list[dict[str, Any]],
    ) -> set[int]:
        """Collect all available page numbers."""

        result: set[int] = set()

        document_pages = getattr(
            document,
            "pages",
            {},
        )

        if isinstance(document_pages, dict):
            for page_number in document_pages:
                try:
                    result.add(int(page_number))
                except (TypeError, ValueError):
                    pass

        for block in blocks:
            result.update(block["page_numbers"])

        for table in tables:
            result.update(table["page_numbers"])

        for picture in pictures:
            result.update(picture["page_numbers"])

        if not result and (
            blocks or tables or pictures
        ):
            result.add(1)

        return result

    def _provenance(
        self,
        item: Any,
    ) -> list[dict[str, Any]]:
        """Extract page-number and bounding-box provenance."""

        result: list[dict[str, Any]] = []

        for provenance in (
            getattr(item, "prov", []) or []
        ):
            bbox = getattr(
                provenance,
                "bbox",
                None,
            )

            result.append(
                {
                    "page_number": getattr(
                        provenance,
                        "page_no",
                        None,
                    ),
                    "bbox": self._bbox(bbox),
                    "character_span": self._json_safe(
                        getattr(
                            provenance,
                            "charspan",
                            None,
                        )
                    ),
                }
            )

        return result

    @staticmethod
    def _bbox(
        bbox: Any,
    ) -> dict[str, Any] | None:
        """Serialize a Docling bounding box."""

        if bbox is None:
            return None

        if hasattr(bbox, "model_dump"):
            return PDFParser._json_safe(
                bbox.model_dump()
            )

        if hasattr(bbox, "dict"):
            return PDFParser._json_safe(
                bbox.dict()
            )

        return {
            key: PDFParser._json_safe(
                getattr(bbox, key)
            )
            for key in (
                "l",
                "t",
                "r",
                "b",
                "coord_origin",
            )
            if hasattr(bbox, key)
        }

    def _annotations(
        self,
        item: Any,
    ) -> list[dict[str, Any]]:
        """Serialize available Docling annotations."""

        result: list[dict[str, Any]] = []

        for annotation in (
            getattr(item, "annotations", None)
            or []
        ):
            if hasattr(annotation, "model_dump"):
                data = annotation.model_dump(
                    mode="json"
                )
            elif hasattr(annotation, "dict"):
                data = annotation.dict()
            else:
                data = {
                    "type": type(
                        annotation
                    ).__name__,
                    "value": str(annotation),
                }

            result.append(
                self._json_safe(data)
            )

        return result

    @staticmethod
    def _item_label(item: Any) -> str:
        """Return normalized Docling item label."""

        label = getattr(item, "label", None)

        if label is None:
            return (
                type(item).__name__
                .removesuffix("Item")
                .lower()
            )

        if hasattr(label, "value"):
            return str(label.value).lower()

        value = str(label)

        if "." in value:
            value = value.split(".")[-1]

        return value.lower()

    @staticmethod
    def _item_text(item: Any) -> str:
        """Return item text when available."""

        text = getattr(item, "text", None)

        return str(text).strip() if text else ""

    @staticmethod
    def _item_reference(
        item: Any,
        fallback: str,
    ) -> str:
        """Return stable Docling item reference."""

        reference = getattr(
            item,
            "self_ref",
            None,
        )

        return str(reference) if reference else fallback

    @staticmethod
    def _safe_string(value: Any) -> str:
        """Convert a table cell to a safe string."""

        if value is None:
            return ""

        try:
            if value != value:
                return ""
        except Exception:
            pass

        return str(value).strip()

    @staticmethod
    def _json_safe(value: Any) -> Any:
        """Convert custom values into JSON-safe values."""

        if value is None:
            return None

        if isinstance(
            value,
            (str, int, float, bool),
        ):
            return value

        if hasattr(value, "value"):
            return PDFParser._json_safe(
                value.value
            )

        if isinstance(value, (list, tuple)):
            return [
                PDFParser._json_safe(item)
                for item in value
            ]

        if isinstance(value, dict):
            return {
                str(key): PDFParser._json_safe(
                    child
                )
                for key, child in value.items()
            }

        return str(value)

    @staticmethod
    def _document_name(
        document: Any,
    ) -> str | None:
        """Return Docling document name."""

        name = getattr(document, "name", None)

        return str(name) if name else None

    @staticmethod
    def _quality_score(
        total_pages: int,
        empty_pages: int,
    ) -> float:
        """Calculate basic page-coverage quality score."""

        if total_pages <= 0:
            return 0.0

        return round(
            (total_pages - empty_pages)
            / total_pages,
            4,
        )

    @staticmethod
    def _generate_document_warnings(
        pages: list[dict[str, Any]],
        tables: list[dict[str, Any]],
        pictures: list[dict[str, Any]],
    ) -> list[str]:
        """Generate document-level warnings."""

        warnings: list[str] = []

        failed_ocr_pages = [
            page["page_number"]
            for page in pages
            if (
                page["ocr"]["applied"]
                and not page["ocr"]["success"]
            )
        ]

        failed_tables = [
            table
            for table in tables
            if table["warning"]
        ]

        unclassified_pictures = [
            picture
            for picture in pictures
            if not picture[
                "classification"
            ]["primary_label"]
        ]

        if failed_ocr_pages:
            warnings.append(
                "OCR returned no usable text on pages: "
                f"{failed_ocr_pages}"
            )

        if failed_tables:
            warnings.append(
                f"{len(failed_tables)} table(s) could "
                "not be exported to Markdown."
            )

        if unclassified_pictures:
            warnings.append(
                f"{len(unclassified_pictures)} picture(s) "
                "were detected without a confident type."
            )

        return warnings

    def save_json(
        self,
        data: dict[str, Any],
        output_path: Path,
    ) -> None:
        """Save parser output atomically."""

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = output_path.with_suffix(
            output_path.suffix + ".tmp"
        )

        with temporary_path.open(
            mode="w",
            encoding="utf-8",
        ) as output_file:
            json.dump(
                data,
                output_file,
                indent=2,
                ensure_ascii=False,
                default=str,
            )

        temporary_path.replace(output_path)

    @staticmethod
    def save_markdown(
        markdown: str,
        output_path: Path,
    ) -> None:
        """Save the complete Docling Markdown output."""

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path.write_text(
            markdown,
            encoding="utf-8",
        )

    @staticmethod
    def _validate_file(file_path: Path) -> None:
        """Validate input PDF path."""

        if not file_path.exists():
            raise FileNotFoundError(
                f"File does not exist: {file_path}"
            )

        if not file_path.is_file():
            raise ValueError(
                f"Path is not a file: {file_path}"
            )

        if file_path.suffix.lower() != ".pdf":
            raise ValueError(
                f"Unsupported file type: "
                f"{file_path.suffix}"
            )

    @staticmethod
    def _validate_page_range(
        page_range: tuple[int, int] | None,
    ) -> None:
        """Validate optional one-based page range."""

        if page_range is None:
            return

        start_page, end_page = page_range

        if start_page < 1:
            raise ValueError(
                "Page range start must be at least 1."
            )

        if end_page < start_page:
            raise ValueError(
                "Page range end cannot be smaller "
                "than start."
            )

    def _failed_result(
        self,
        file_path: Path,
        document_id: str,
        document_hash: str,
        started_at: str,
        page_range: tuple[int, int] | None,
        error: Exception,
    ) -> dict[str, Any]:
        """Return standard failure schema."""

        return {
            "document_id": document_id,
            "document_hash": document_hash,
            "source": {
                "file_name": file_path.name,
                "file_type": "pdf",
                "file_size_bytes": (
                    file_path.stat().st_size
                ),
                "source_path": str(
                    file_path.resolve()
                ),
            },
            "document_metadata": {
                "page_count": 0,
                "processed_page_range": (
                    list(page_range)
                    if page_range
                    else None
                ),
                "title": None,
            },
            "processing": {
                "parser_name": self.PARSER_NAME,
                "parser_version": self.PARSER_VERSION,
                "processing_started_at": started_at,
                "processing_completed_at": (
                    self._timestamp()
                ),
                "status": "failed",
                "strategy": "adaptive_two_pass",
            },
            "content_summary": {
                "total_blocks": 0,
                "total_tables": 0,
                "total_pictures": 0,
                "label_counts": {},
                "page_type_counts": {},
                "ocr_required_page_count": 0,
                "ocr_required_pages": [],
            },
            "pages": [],
            "blocks": [],
            "tables": [],
            "pictures": [],
            "markdown": "",
            "quality": {
                "pages_processed": 0,
                "pages_with_text": 0,
                "pages_with_tables": 0,
                "pages_with_pictures": 0,
                "pages_requiring_ocr": 0,
                "ocr_pages_processed": 0,
                "empty_pages": 0,
                "failed_pages": 1,
                "overall_quality_score": 0.0,
            },
            "warnings": [],
            "errors": [
                {
                    "scope": "document",
                    "error_type": (
                        type(error).__name__
                    ),
                    "message": str(error),
                }
            ],
        }

    @staticmethod
    def _timestamp() -> str:
        """Return timezone-aware UTC timestamp."""

        return datetime.now(timezone.utc).isoformat()