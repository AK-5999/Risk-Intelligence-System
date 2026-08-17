from __future__ import annotations

import argparse
import json
import logging
import sys

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from normalization import DocumentNormalizer
from parsing.pdf_parser import PDFParser
from registry import ProcessingRegistry


class ParsingComponent:
    """
    Phase 1 Document Parsing Component.

    Pipeline:
        Input PDF
            ↓
        Document Identification (SHA-256)
            ↓
        Physical Extraction
            ↓
        Merge with existing raw document
            ↓
        Normalize current extraction
            ↓
        Merge with existing canonical document
            ↓
        Persistent document-level JSON

    Persistence rule:
    - One raw JSON per source document
    - One canonical JSON per source document
    - Existing pages are replaced
    - Missing pages are appended
    - Final pages are sorted by page number
    """

    def __init__(
        self,
        force_reprocess: bool = False,
    ) -> None:

        # =====================================================
        # PROJECT PATHS
        # =====================================================

        self.src_dir = (
            Path(__file__)
            .resolve()
            .parent
        )

        self.phase1_dir = (
            self.src_dir.parent
        )

        self.raw_output_dir = (
            self.phase1_dir
            / "output"
            / "raw"
        )

        self.normalized_output_dir = (
            self.phase1_dir
            / "output"
            / "normalized"
        )

        self.logger_dir = (
            self.phase1_dir
            / "logger"
        )

        self.registry_dir = (
            self.phase1_dir
            / "registry_report"
        )

        self._create_directories()

        # =====================================================
        # LOGGER
        # =====================================================

        self.log_path = (
            self._configure_logger()
        )

        # =====================================================
        # REGISTRY
        # =====================================================

        self.registry = ProcessingRegistry(
            registry_path=(
                self.registry_dir
                / "processed_files.json"
            )
        )

        # =====================================================
        # PARSER
        # =====================================================

        self.parser = PDFParser(
            enable_table_structure=True,
            enable_picture_classification=True,
            enable_chart_extraction=True,
            generate_picture_images=True,
            images_scale=2.0,
            minimum_native_text_characters=20,
        )

        # =====================================================
        # NORMALIZER
        # =====================================================

        self.normalizer = (
            DocumentNormalizer()
        )

        self.force_reprocess = (
            force_reprocess
        )

    # =========================================================
    # DIRECTORY SETUP
    # =========================================================

    def _create_directories(
        self,
    ) -> None:

        directories = [
            self.raw_output_dir,
            self.normalized_output_dir,
            self.logger_dir,
            self.registry_dir,
        ]

        for directory in directories:

            directory.mkdir(
                parents=True,
                exist_ok=True,
            )

    # =========================================================
    # LOGGER
    # =========================================================

    def _configure_logger(
        self,
    ) -> Path:

        timestamp = (
            datetime.now()
            .strftime(
                "%Y%m%d_%H%M%S_%f"
            )
        )

        log_path = (
            self.logger_dir
            / f"run_{timestamp}.txt"
        )

        logger = logging.getLogger(
            "parsing_component"
        )

        logger.setLevel(
            logging.INFO
        )

        logger.handlers.clear()

        file_handler = logging.FileHandler(
            log_path,
            mode="w",
            encoding="utf-8",
        )

        formatter = logging.Formatter(
            (
                "%(asctime)s | "
                "%(levelname)s | "
                "%(message)s"
            ),
            datefmt=(
                "%Y-%m-%d %H:%M:%S"
            ),
        )

        file_handler.setFormatter(
            formatter
        )

        logger.addHandler(
            file_handler
        )

        self.logger = logger

        return log_path

    # =========================================================
    # MAIN PROCESSING
    # =========================================================

    def process(
        self,
        input_file: str | Path,
        page_range: tuple[int, int] | None = None,
    ) -> dict[str, Any] | None:

        input_file = (
            Path(input_file)
            .expanduser()
            .resolve()
        )

        registry_key: str | None = None

        self.logger.info(
            "=" * 72
        )

        self.logger.info(
            "PARSING COMPONENT STARTED"
        )

        self.logger.info(
            "=" * 72
        )

        self.logger.info(
            "Input file: %s",
            input_file,
        )

        self.logger.info(
            "Requested page range: %s",
            page_range or "FULL DOCUMENT",
        )

        self.logger.info(
            "Force reprocess: %s",
            self.force_reprocess,
        )

        try:

            # =================================================
            # 1. INPUT VALIDATION
            # =================================================

            self._validate_input(
                input_file
            )

            self.logger.info(
                "Input validation completed"
            )

            # =================================================
            # 2. DOCUMENT HASH
            # =================================================

            self.logger.info(
                "Calculating document SHA-256 hash"
            )

            document_hash = (
                self.parser.calculate_hash(
                    input_file
                )
            )

            self.logger.info(
                "Document hash: %s",
                document_hash,
            )

            # =================================================
            # 3. STABLE DOCUMENT-LEVEL OUTPUT NAME
            # =================================================

            output_name = (
                self._build_output_name(
                    input_file=input_file,
                    document_hash=document_hash,
                )
            )

            raw_output_path = (
                self.raw_output_dir
                / f"{output_name}.json"
            )

            normalized_output_path = (
                self.normalized_output_dir
                / f"{output_name}.json"
            )

            self.logger.info(
                "Raw document output: %s",
                raw_output_path,
            )

            self.logger.info(
                "Canonical document output: %s",
                normalized_output_path,
            )

            # =================================================
            # 4. LOAD EXISTING DOCUMENT STATE
            # =================================================

            existing_raw = (
                self._load_json(
                    raw_output_path
                )
            )

            existing_canonical = (
                self._load_json(
                    normalized_output_path
                )
            )

            existing_pages = (
                self._get_existing_page_numbers(
                    existing_canonical
                )
            )

            self.logger.info(
                "Existing canonical pages: %s",
                existing_pages,
            )

            # =================================================
            # 5. CHECK REQUESTED PAGES
            # =================================================

            requested_pages = (
                self._requested_page_numbers(
                    page_range
                )
            )

            if requested_pages is not None:

                self.logger.info(
                    "Requested pages: %s",
                    requested_pages,
                )

                already_available = (
                    set(requested_pages)
                    .issubset(
                        set(existing_pages)
                    )
                )

                if (
                    already_available
                    and not self.force_reprocess
                ):

                    self.logger.info(
                        (
                            "All requested pages already "
                            "exist in canonical document."
                        )
                    )

                    self.logger.info(
                        "Processing skipped."
                    )

                    return existing_canonical

            # =================================================
            # 6. REGISTRY KEY
            # =================================================
            #
            # Temporary compatibility:
            # registry is still range-based.
            #
            # Next iteration will make registry document-based.
            # =================================================

            registry_key = (
                self.registry.build_key(
                    document_hash=document_hash,
                    page_range=page_range,
                    parser_name=(
                        self.parser.PARSER_NAME
                    ),
                    parser_version=(
                        self.parser.PARSER_VERSION
                    ),
                )
            )

            self.logger.info(
                "Registry key: %s",
                registry_key,
            )

            # =================================================
            # 7. REGISTRY → PROCESSING
            # =================================================

            self.registry.mark_processing(
                registry_key=registry_key,
                document_hash=document_hash,
                file_path=input_file,
                raw_output_json=raw_output_path,
                canonical_output_json=(
                    normalized_output_path
                ),
                page_range=page_range,
                parser_name=(
                    self.parser.PARSER_NAME
                ),
                parser_version=(
                    self.parser.PARSER_VERSION
                ),
            )

            self.logger.info(
                "Registry updated: PROCESSING"
            )

            # =================================================
            # 8. PHYSICAL EXTRACTION
            # =================================================

            self.logger.info(
                (
                    "Starting physical extraction "
                    "for requested scope"
                )
            )

            new_raw_document = (
                self.parser.parse(
                    file_path=input_file,
                    document_hash=document_hash,
                    page_range=page_range,
                )
            )

            parser_status = (
                new_raw_document
                .get(
                    "processing",
                    {},
                )
                .get(
                    "status"
                )
            )

            self.logger.info(
                "Parser status: %s",
                parser_status,
            )

            # =================================================
            # 9. PARSER FAILURE
            # =================================================

            if parser_status == "failed":

                self.registry.mark_failed(
                    registry_key=registry_key,
                    error=(
                        "Physical PDF extraction failed"
                    ),
                    result=new_raw_document,
                )

                self.logger.error(
                    "Physical PDF extraction failed"
                )

                return new_raw_document

            new_page_numbers = (
                self._get_page_numbers(
                    new_raw_document
                )
            )

            self.logger.info(
                "Pages extracted in current run: %s",
                new_page_numbers,
            )

            # =================================================
            # 10. MERGE RAW DOCUMENT
            # =================================================

            merged_raw_document = (
                self._merge_raw_document(
                    existing=existing_raw,
                    new=new_raw_document,
                )
            )

            self._save_json(
                data=merged_raw_document,
                output_path=raw_output_path,
            )

            self.logger.info(
                "Merged raw document saved"
            )

            # =================================================
            # 11. NORMALIZE ONLY CURRENT EXTRACTION
            # =================================================
            #
            # Important:
            # We do NOT normalize all previously processed
            # pages again.
            # =================================================

            self.logger.info(
                (
                    "Normalizing current "
                    "extraction only"
                )
            )

            new_canonical_document = (
                self.normalizer.normalize(
                    new_raw_document
                )
            )

            new_canonical_dict = (
                new_canonical_document
                .to_dict()
            )

            # =================================================
            # 12. MERGE CANONICAL DOCUMENT
            # =================================================

            merged_canonical = (
                self._merge_canonical_document(
                    existing=existing_canonical,
                    new=new_canonical_dict,
                )
            )

            self._save_json(
                data=merged_canonical,
                output_path=(
                    normalized_output_path
                ),
            )

            self.logger.info(
                "Merged canonical document saved"
            )

            # =================================================
            # 13. REGISTRY → COMPLETED
            # =================================================

            self.registry.mark_completed(
                registry_key=registry_key,
                result=new_raw_document,
                raw_output_json=(
                    raw_output_path
                ),
                canonical_output_json=(
                    normalized_output_path
                ),
            )

            self.logger.info(
                "Registry updated: COMPLETED"
            )

            # =================================================
            # 14. SUMMARY
            # =================================================

            self._log_summary(
                merged_canonical
            )

            final_pages = (
                self._get_page_numbers(
                    merged_canonical
                )
            )

            self.logger.info(
                "Final stored pages: %s",
                final_pages,
            )

            self.logger.info(
                "=" * 72
            )

            self.logger.info(
                "PARSING COMPONENT COMPLETED"
            )

            self.logger.info(
                "=" * 72
            )

            return merged_canonical

        # =====================================================
        # USER INTERRUPT
        # =====================================================

        except KeyboardInterrupt:

            self.logger.warning(
                "Processing interrupted by user"
            )

            if registry_key:

                try:

                    self.registry.mark_failed(
                        registry_key=registry_key,
                        error=(
                            "Processing interrupted by user"
                        ),
                    )

                except Exception:

                    self.logger.exception(
                        (
                            "Failed to update registry "
                            "after interruption"
                        )
                    )

            raise

        # =====================================================
        # UNEXPECTED FAILURE
        # =====================================================

        except Exception as error:

            self.logger.exception(
                (
                    "Processing failed: "
                    "%s: %s"
                ),
                type(error).__name__,
                error,
            )

            if registry_key:

                try:

                    self.registry.mark_failed(
                        registry_key=registry_key,
                        error=error,
                    )

                except Exception as registry_error:

                    self.logger.exception(
                        (
                            "Failed to update registry "
                            "after pipeline failure: %s"
                        ),
                        registry_error,
                    )

            raise

    # =========================================================
    # RAW DOCUMENT MERGE
    # =========================================================

    def _merge_raw_document(
        self,
        existing: dict[str, Any] | None,
        new: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Merge a new partial parser result into an existing
        raw document.

        Rule:
        - Pages in the new extraction replace existing pages.
        - Previously unseen pages are appended.
        - Blocks/tables/pictures belonging to replaced pages
          are removed before inserting new ones.

        This avoids collisions from Docling self references such
        as '#/texts/0' being reused across separate conversions.
        """

        if existing is None:

            merged = dict(new)

        else:

            merged = dict(existing)

            new_pages = set(
                self._get_page_numbers(
                    new
                )
            )

            # -------------------------------------------------
            # Pages
            # -------------------------------------------------

            merged["pages"] = (
                self._merge_pages(
                    existing_pages=(
                        existing.get(
                            "pages",
                            [],
                        )
                    ),
                    new_pages=(
                        new.get(
                            "pages",
                            [],
                        )
                    ),
                )
            )

            # -------------------------------------------------
            # Blocks
            # -------------------------------------------------

            merged["blocks"] = (
                self._replace_items_for_pages(
                    existing_items=(
                        existing.get(
                            "blocks",
                            [],
                        )
                    ),
                    new_items=(
                        new.get(
                            "blocks",
                            [],
                        )
                    ),
                    replaced_pages=new_pages,
                )
            )

            # -------------------------------------------------
            # Tables
            # -------------------------------------------------

            merged["tables"] = (
                self._replace_items_for_pages(
                    existing_items=(
                        existing.get(
                            "tables",
                            [],
                        )
                    ),
                    new_items=(
                        new.get(
                            "tables",
                            [],
                        )
                    ),
                    replaced_pages=new_pages,
                )
            )

            # -------------------------------------------------
            # Pictures
            # -------------------------------------------------

            merged["pictures"] = (
                self._replace_items_for_pages(
                    existing_items=(
                        existing.get(
                            "pictures",
                            [],
                        )
                    ),
                    new_items=(
                        new.get(
                            "pictures",
                            [],
                        )
                    ),
                    replaced_pages=new_pages,
                )
            )

            # Preserve original stable document identity.
            merged["document_id"] = (
                existing.get(
                    "document_id"
                )
                or new.get(
                    "document_id"
                )
            )

            merged["document_hash"] = (
                new.get(
                    "document_hash"
                )
                or existing.get(
                    "document_hash"
                )
            )

            merged["source"] = (
                new.get(
                    "source"
                )
                or existing.get(
                    "source",
                    {},
                )
            )

            # Latest parser execution metadata.
            merged["processing"] = (
                new.get(
                    "processing",
                    {},
                )
            )

            # Aggregated warnings/errors.
            merged["warnings"] = (
                self._merge_unique_strings(
                    existing.get(
                        "warnings",
                        [],
                    ),
                    new.get(
                        "warnings",
                        [],
                    ),
                )
            )

            merged["errors"] = (
                new.get(
                    "errors",
                    [],
                )
            )

        # -----------------------------------------------------
        # Rebuild aggregated document metadata
        # -----------------------------------------------------

        processed_pages = (
            self._get_page_numbers(
                merged
            )
        )

        document_metadata = dict(
            merged.get(
                "document_metadata",
                {},
            )
        )

        document_metadata[
            "processed_pages"
        ] = processed_pages

        document_metadata[
            "processed_page_count"
        ] = len(
            processed_pages
        )

        # Existing field name "page_count" originally represented
        # pages processed in one parser call. For merged document,
        # make it explicitly represent stored/processed pages.
        document_metadata[
            "page_count"
        ] = len(
            processed_pages
        )

        # A single range may no longer represent the document.
        document_metadata[
            "processed_page_range"
        ] = None

        merged[
            "document_metadata"
        ] = document_metadata

        # -----------------------------------------------------
        # Recalculate summaries
        # -----------------------------------------------------

        self._rebuild_raw_summary(
            merged
        )

        # Markdown from separate parser runs cannot safely be
        # concatenated while preserving layout/reading order.
        #
        # The canonical representation is now our downstream
        # artifact, so do not claim this is full-document Markdown.
        merged["markdown"] = None

        merged[
            "markdown_status"
        ] = (
            "not_merged_across_partial_runs"
        )

        return merged

    # =========================================================
    # CANONICAL DOCUMENT MERGE
    # =========================================================

    def _merge_canonical_document(
        self,
        existing: dict[str, Any] | None,
        new: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Merge normalized page-level output.

        Same page number:
            replace existing page.

        New page number:
            append.

        Final pages are sorted.
        """

        if existing is None:

            merged = dict(new)

        else:

            merged = {
                **existing,
                **new,
            }

            merged["pages"] = (
                self._merge_pages(
                    existing_pages=(
                        existing.get(
                            "pages",
                            [],
                        )
                    ),
                    new_pages=(
                        new.get(
                            "pages",
                            [],
                        )
                    ),
                )
            )

            # Preserve first document identity instead of replacing
            # it with a new UUID from every partial parser call.
            merged["document_id"] = (
                existing.get(
                    "document_id"
                )
                or new.get(
                    "document_id"
                )
            )

            merged["document_hash"] = (
                new.get(
                    "document_hash"
                )
                or existing.get(
                    "document_hash"
                )
            )

        processed_pages = (
            self._get_page_numbers(
                merged
            )
        )

        metadata = dict(
            merged.get(
                "metadata",
                {},
            )
        )

        metadata[
            "processed_pages"
        ] = processed_pages

        metadata[
            "processed_page_count"
        ] = len(
            processed_pages
        )

        # One range is no longer meaningful after merging.
        metadata[
            "processed_page_range"
        ] = None

        merged[
            "metadata"
        ] = metadata

        normalization = dict(
            merged.get(
                "normalization",
                {},
            )
        )

        normalization[
            "document_merge_applied"
        ] = True

        normalization[
            "merge_strategy"
        ] = (
            "replace_existing_page_or_append_missing_page"
        )

        merged[
            "normalization"
        ] = normalization

        return merged

    # =========================================================
    # PAGE MERGING
    # =========================================================

    @staticmethod
    def _merge_pages(
        existing_pages: list[dict[str, Any]],
        new_pages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Merge by page_number.

        Dictionary assignment naturally provides:

        existing page → replace
        missing page  → append
        """

        page_map: dict[
            int,
            dict[str, Any],
        ] = {}

        for page in existing_pages:

            page_number = page.get(
                "page_number"
            )

            if page_number is None:
                continue

            page_map[
                int(page_number)
            ] = page

        for page in new_pages:

            page_number = page.get(
                "page_number"
            )

            if page_number is None:
                continue

            page_map[
                int(page_number)
            ] = page

        return [
            page_map[
                page_number
            ]
            for page_number
            in sorted(
                page_map
            )
        ]

    # =========================================================
    # RAW ITEM REPLACEMENT
    # =========================================================

    @staticmethod
    def _replace_items_for_pages(
        existing_items: list[
            dict[str, Any]
        ],
        new_items: list[
            dict[str, Any]
        ],
        replaced_pages: set[int],
    ) -> list[dict[str, Any]]:
        """
        Remove existing blocks/tables/pictures belonging to pages
        being reprocessed, then append newly extracted items.

        We intentionally do NOT merge solely by Docling block_id
        because partial conversions can reuse IDs like:

            #/texts/0
            #/tables/0
            #/pictures/0
        """

        retained_items = []

        for item in existing_items:

            item_pages = {
                int(page)
                for page
                in item.get(
                    "page_numbers",
                    [],
                )
                if page is not None
            }

            if (
                item_pages
                & replaced_pages
            ):
                continue

            retained_items.append(
                item
            )

        return [
            *retained_items,
            *new_items,
        ]

    # =========================================================
    # RAW SUMMARY REBUILD
    # =========================================================

    @staticmethod
    def _rebuild_raw_summary(
        document: dict[str, Any],
    ) -> None:
        """
        Recalculate summary and basic page-level quality after
        multiple partial parser results are merged.
        """

        pages = document.get(
            "pages",
            [],
        )

        blocks = document.get(
            "blocks",
            [],
        )

        tables = document.get(
            "tables",
            [],
        )

        pictures = document.get(
            "pictures",
            [],
        )

        label_counts = Counter(
            str(
                block.get(
                    "type",
                    "unknown",
                )
            )
            for block in blocks
        )

        page_type_counts = Counter(
            str(
                page.get(
                    "page_type",
                    "unknown",
                )
            )
            for page in pages
        )

        pages_with_text = sum(
            1
            for page in pages
            if (
                page.get(
                    "contains",
                    {},
                )
                .get(
                    "text",
                    False,
                )
            )
        )

        pages_with_tables = sum(
            1
            for page in pages
            if (
                page.get(
                    "contains",
                    {},
                )
                .get(
                    "table",
                    False,
                )
            )
        )

        pages_with_pictures = sum(
            1
            for page in pages
            if (
                page.get(
                    "contains",
                    {},
                )
                .get(
                    "picture",
                    False,
                )
            )
        )

        pages_requiring_ocr = [
            page.get(
                "page_number"
            )
            for page in pages
            if (
                page.get(
                    "ocr",
                    {},
                )
                .get(
                    "required",
                    False,
                )
            )
        ]

        ocr_pages_processed = sum(
            1
            for page in pages
            if (
                page.get(
                    "ocr",
                    {},
                )
                .get(
                    "applied",
                    False,
                )
            )
        )

        empty_pages = sum(
            1
            for page in pages
            if (
                page.get(
                    "page_type"
                )
                == "empty_or_unresolved"
            )
        )

        total_pages = len(
            pages
        )

        document[
            "content_summary"
        ] = {
            "total_blocks": len(
                blocks
            ),
            "total_tables": len(
                tables
            ),
            "total_pictures": len(
                pictures
            ),
            "label_counts": dict(
                label_counts
            ),
            "page_type_counts": dict(
                page_type_counts
            ),
            "ocr_required_page_count": (
                len(
                    pages_requiring_ocr
                )
            ),
            "ocr_required_pages": (
                sorted(
                    page
                    for page
                    in pages_requiring_ocr
                    if page is not None
                )
            ),
        }

        document[
            "quality"
        ] = {
            "pages_processed": (
                total_pages
            ),
            "pages_with_text": (
                pages_with_text
            ),
            "pages_with_tables": (
                pages_with_tables
            ),
            "pages_with_pictures": (
                pages_with_pictures
            ),
            "pages_requiring_ocr": (
                len(
                    pages_requiring_ocr
                )
            ),
            "ocr_pages_processed": (
                ocr_pages_processed
            ),
            "empty_pages": (
                empty_pages
            ),
            "failed_pages": 0,

            # This remains page-coverage only.
            # Actual extraction accuracy belongs
            # to the evaluation component.
            "overall_quality_score": (
                round(
                    (
                        total_pages
                        - empty_pages
                    )
                    / total_pages,
                    4,
                )
                if total_pages
                else 0.0
            ),
        }

    # =========================================================
    # EXISTING / REQUESTED PAGE HELPERS
    # =========================================================

    @staticmethod
    def _get_page_numbers(
        document: dict[str, Any]
        | None,
    ) -> list[int]:

        if not document:
            return []

        page_numbers = []

        for page in document.get(
            "pages",
            [],
        ):

            page_number = page.get(
                "page_number"
            )

            if page_number is None:
                continue

            page_numbers.append(
                int(page_number)
            )

        return sorted(
            set(
                page_numbers
            )
        )

    def _get_existing_page_numbers(
        self,
        canonical_document: (
            dict[str, Any]
            | None
        ),
    ) -> list[int]:

        return self._get_page_numbers(
            canonical_document
        )

    @staticmethod
    def _requested_page_numbers(
        page_range: tuple[
            int,
            int,
        ]
        | None,
    ) -> list[int] | None:

        if page_range is None:
            return None

        start_page, end_page = (
            page_range
        )

        return list(
            range(
                start_page,
                end_page + 1,
            )
        )

    # =========================================================
    # UNIQUE STRING MERGE
    # =========================================================

    @staticmethod
    def _merge_unique_strings(
        first: list[str],
        second: list[str],
    ) -> list[str]:

        return list(
            dict.fromkeys(
                [
                    *first,
                    *second,
                ]
            )
        )

    # =========================================================
    # INPUT VALIDATION
    # =========================================================

    def _validate_input(
        self,
        input_file: Path,
    ) -> None:

        if not input_file.exists():

            raise FileNotFoundError(
                f"File not found: "
                f"{input_file}"
            )

        if not input_file.is_file():

            raise ValueError(
                (
                    "Input path is not "
                    f"a file: {input_file}"
                )
            )

        if not self.parser.can_parse(
            input_file
        ):

            raise ValueError(
                (
                    "Unsupported or invalid "
                    f"PDF: {input_file}"
                )
            )

    # =========================================================
    # LOAD JSON
    # =========================================================

    @staticmethod
    def _load_json(
        input_path: Path,
    ) -> dict[str, Any] | None:
        """
        Load an existing output document.

        Missing or empty file means no existing state.
        """

        if not input_path.exists():
            return None

        content = input_path.read_text(
            encoding="utf-8"
        ).strip()

        if not content:
            return None

        try:

            data = json.loads(
                content
            )

        except json.JSONDecodeError as error:

            raise ValueError(
                (
                    "Existing document JSON "
                    "is invalid: "
                    f"{input_path}"
                )
            ) from error

        if not isinstance(
            data,
            dict,
        ):

            raise ValueError(
                (
                    "Existing document JSON "
                    "root must be an object: "
                    f"{input_path}"
                )
            )

        return data

    # =========================================================
    # SAVE JSON
    # =========================================================

    @staticmethod
    def _save_json(
        data: dict[str, Any],
        output_path: Path,
    ) -> None:
        """
        Atomic JSON save.

        Prevents partially-written files if the process fails
        while writing.
        """

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = (
            output_path.with_suffix(
                output_path.suffix
                + ".tmp"
            )
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

        temporary_path.replace(
            output_path
        )

    # =========================================================
    # OUTPUT NAME
    # =========================================================

    @staticmethod
    def _build_output_name(
        input_file: Path,
        document_hash: str,
    ) -> str:
        """
        Stable document-level output name.

        Page range is deliberately NOT included.

        Same source document:
            same SHA-256
            same output JSON
        """

        return (
            f"{input_file.stem}_"
            f"{document_hash[:12]}"
        )

    # =========================================================
    # SUMMARY LOGGER
    # =========================================================

    def _log_summary(
        self,
        document: dict[str, Any],
    ) -> None:

        pages = document.get(
            "pages",
            [],
        )

        block_count = sum(
            len(
                page.get(
                    "blocks",
                    [],
                )
            )
            for page in pages
        )

        table_count = sum(
            1
            for page in pages
            for block in page.get(
                "blocks",
                [],
            )
            if (
                block.get(
                    "type"
                )
                == "table"
            )
        )

        heading_count = sum(
            1
            for page in pages
            for block in page.get(
                "blocks",
                [],
            )
            if (
                block.get(
                    "type"
                )
                == "heading"
            )
        )

        text_count = sum(
            1
            for page in pages
            for block in page.get(
                "blocks",
                [],
            )
            if (
                block.get(
                    "type"
                )
                == "text"
            )
        )

        chart_count = sum(
            1
            for page in pages
            for block in page.get(
                "blocks",
                [],
            )
            if (
                block.get(
                    "type"
                )
                == "chart"
            )
        )

        diagram_count = sum(
            1
            for page in pages
            for block in page.get(
                "blocks",
                [],
            )
            if (
                block.get(
                    "type"
                )
                == "diagram"
            )
        )

        image_count = sum(
            1
            for page in pages
            for block in page.get(
                "blocks",
                [],
            )
            if (
                block.get(
                    "type"
                )
                == "image"
            )
        )

        page_numbers = (
            self._get_page_numbers(
                document
            )
        )

        self.logger.info(
            "-" * 72
        )

        self.logger.info(
            "CANONICAL DOCUMENT SUMMARY"
        )

        self.logger.info(
            "-" * 72
        )

        self.logger.info(
            "Stored pages: %s",
            page_numbers,
        )

        self.logger.info(
            "Page count: %s",
            len(
                page_numbers
            ),
        )

        self.logger.info(
            "Total canonical blocks: %s",
            block_count,
        )

        self.logger.info(
            "Text blocks: %s",
            text_count,
        )

        self.logger.info(
            "Headings: %s",
            heading_count,
        )

        self.logger.info(
            "Tables: %s",
            table_count,
        )

        self.logger.info(
            "Charts: %s",
            chart_count,
        )

        self.logger.info(
            "Diagrams: %s",
            diagram_count,
        )

        self.logger.info(
            "Images: %s",
            image_count,
        )

        self.logger.info(
            "-" * 72
        )


# =============================================================
# COMMAND LINE
# =============================================================


def parse_arguments() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Risk Intelligence System "
            "- Phase 1 Document Parsing"
        )
    )

    parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=str,
        help=(
            "Path to the input PDF document."
        ),
    )

    parser.add_argument(
        "--pages",
        nargs=2,
        type=int,
        metavar=(
            "START",
            "END",
        ),
        help=(
            "Optional one-based page range. "
            "Example: --pages 51 51"
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Reprocess requested pages even "
            "if they already exist."
        ),
    )

    return parser.parse_args()


# =============================================================
# MAIN
# =============================================================


def main() -> None:

    args = parse_arguments()

    page_range = (
        tuple(args.pages)
        if args.pages
        else None
    )

    component = ParsingComponent(
        force_reprocess=(
            args.force
        )
    )

    try:

        component.process(
            input_file=args.input,
            page_range=page_range,
        )

    except KeyboardInterrupt:

        sys.exit(130)

    except Exception:

        # Detailed error already written
        # to run-specific log.
        sys.exit(1)


if __name__ == "__main__":
    main()