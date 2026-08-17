from __future__ import annotations

import argparse
import json
import logging
import sys

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
        Physical Extraction
            ↓
        Raw Parser Representation
            ↓
        Normalization
            ↓
        Canonical Document Representation

    Responsibilities:
    - Resolve project-relative paths
    - Validate input document
    - Calculate document hash
    - Manage processing registry
    - Execute PDF parsing
    - Save raw parser output
    - Normalize extracted document
    - Save canonical output
    - Maintain run-specific log
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

        # phase1/
        self.phase1_dir = (
            self.src_dir.parent
        )

        # Raw parser output
        self.raw_output_dir = (
            self.phase1_dir
            / "output"
            / "raw"
        )

        # Normalized / canonical output
        self.normalized_output_dir = (
            self.phase1_dir
            / "output"
            / "normalized"
        )

        # Run logs
        self.logger_dir = (
            self.phase1_dir
            / "logger"
        )

        # Processing registry
        self.registry_dir = (
            self.phase1_dir
            / "registry_report"
        )

        # Create folders automatically
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
        # PDF PARSER
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

        # =====================================================
        # PROCESSING CONFIGURATION
        # =====================================================

        self.force_reprocess = (
            force_reprocess
        )

    # =========================================================
    # DIRECTORY SETUP
    # =========================================================

    def _create_directories(
        self,
    ) -> None:
        """
        Create all required Phase 1 directories.
        """

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
        """
        Create one new log file for each execution.
        """

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

        # Prevent duplicated handlers
        # when instantiated multiple times.
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
    # MAIN PROCESSING METHOD
    # =========================================================

    def process(
        self,
        input_file: str | Path,
        page_range: tuple[int, int] | None = None,
    ) -> dict[str, Any] | None:
        """
        Execute the Phase 1 parsing pipeline.

        Parameters
        ----------
        input_file:
            PDF file path.

        page_range:
            Optional one-based page range.

            Example:
                (51, 51)

            None:
                Process the complete document.

        Returns
        -------
        dict | None
            Canonical normalized document.

            Returns None when processing is
            skipped due to an existing completed
            registry record.
        """

        input_file = (
            Path(input_file)
            .expanduser()
            .resolve()
        )

        registry_key: str | None = None

        # =====================================================
        # RUN START
        # =====================================================

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
            "Page range: %s",
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
            # 3. REGISTRY KEY
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
            # 4. OUTPUT PATHS
            # =================================================

            output_name = (
                self._build_output_name(
                    input_file=input_file,
                    document_hash=document_hash,
                    page_range=page_range,
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
                "Raw output path: %s",
                raw_output_path,
            )

            self.logger.info(
                "Canonical output path: %s",
                normalized_output_path,
            )

            self.logger.info(
                "Registry path: %s",
                self.registry.registry_path,
            )

            # =================================================
            # 5. DUPLICATE CHECK
            # =================================================

            if (
                not self.force_reprocess
                and self.registry.is_completed(
                    registry_key=registry_key,
                    verify_output=True,
                )
            ):

                existing = (
                    self.registry.get(
                        registry_key
                    )
                )

                self.logger.info(
                    "Document scope already processed"
                )

                self.logger.info(
                    "Processing skipped"
                )

                if existing:

                    outputs = (
                        existing.get(
                            "outputs",
                            {},
                        )
                    )

                    self.logger.info(
                        "Existing raw output: %s",
                        outputs.get(
                            "raw_json"
                        ),
                    )

                    self.logger.info(
                        "Existing canonical output: %s",
                        outputs.get(
                            "canonical_json"
                        ),
                    )

                return None

            # =================================================
            # 6. REGISTRY → PROCESSING
            # =================================================

            self.registry.mark_processing(
                registry_key=registry_key,
                document_hash=document_hash,
                file_path=input_file,

                raw_output_json=(
                    raw_output_path
                ),

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
            # 7. PHYSICAL EXTRACTION
            # =================================================

            self.logger.info(
                "Starting physical PDF extraction"
            )

            raw_document = (
                self.parser.parse(
                    file_path=input_file,
                    document_hash=document_hash,
                    page_range=page_range,
                )
            )

            parser_status = (
                raw_document
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
            # 8. PARSER FAILURE
            # =================================================

            if parser_status == "failed":

                self.logger.error(
                    "Physical PDF extraction failed"
                )

                self.registry.mark_failed(
                    registry_key=registry_key,
                    error=(
                        "Physical PDF extraction failed"
                    ),
                    result=raw_document,
                )

                self.logger.info(
                    "Registry updated: FAILED"
                )

                return raw_document

            # =================================================
            # 9. SAVE RAW PARSER OUTPUT
            # =================================================

            self._save_json(
                data=raw_document,
                output_path=raw_output_path,
            )

            self.logger.info(
                "Raw parser output saved successfully"
            )

            # =================================================
            # 10. DOCUMENT NORMALIZATION
            # =================================================

            self.logger.info(
                "Starting document normalization"
            )

            canonical_document = (
                self.normalizer.normalize(
                    raw_document
                )
            )

            canonical_dict = (
                canonical_document.to_dict()
            )

            self.logger.info(
                "Document normalization completed"
            )

            # =================================================
            # 11. SAVE CANONICAL OUTPUT
            # =================================================

            self._save_json(
                data=canonical_dict,
                output_path=(
                    normalized_output_path
                ),
            )

            self.logger.info(
                "Canonical document saved successfully"
            )

            # =================================================
            # 12. REGISTRY → COMPLETED
            # =================================================

            self.registry.mark_completed(
                registry_key=registry_key,

                result=raw_document,

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
            # 13. RUN SUMMARY
            # =================================================

            self._log_summary(
                canonical_dict
            )

            # =================================================
            # RUN COMPLETE
            # =================================================

            self.logger.info(
                "=" * 72
            )

            self.logger.info(
                "PARSING COMPONENT COMPLETED"
            )

            self.logger.info(
                "=" * 72
            )

            self.logger.info(
                "Raw output: %s",
                raw_output_path,
            )

            self.logger.info(
                "Canonical output: %s",
                normalized_output_path,
            )

            self.logger.info(
                "Registry: %s",
                self.registry.registry_path,
            )

            self.logger.info(
                "Run log: %s",
                self.log_path,
            )

            return canonical_dict

        # =====================================================
        # USER INTERRUPT
        # =====================================================

        except KeyboardInterrupt:

            self.logger.warning(
                "Processing interrupted by user"
            )

            if registry_key:

                self.registry.mark_failed(
                    registry_key=registry_key,
                    error=(
                        "Processing interrupted by user"
                    ),
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

                    self.logger.info(
                        "Registry updated: FAILED"
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
    # INPUT VALIDATION
    # =========================================================

    def _validate_input(
        self,
        input_file: Path,
    ) -> None:
        """
        Validate input PDF.
        """

        if not input_file.exists():

            raise FileNotFoundError(
                f"File not found: "
                f"{input_file}"
            )

        if not input_file.is_file():

            raise ValueError(
                f"Input path is not a file: "
                f"{input_file}"
            )

        if not self.parser.can_parse(
            input_file
        ):

            raise ValueError(
                f"Unsupported or invalid PDF: "
                f"{input_file}"
            )

    # =========================================================
    # SAVE JSON
    # =========================================================

    @staticmethod
    def _save_json(
        data: dict[str, Any],
        output_path: Path,
    ) -> None:
        """
        Save dictionary as formatted JSON.
        """

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with output_path.open(
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

    # =========================================================
    # OUTPUT FILE NAME
    # =========================================================

    @staticmethod
    def _build_output_name(
        input_file: Path,
        document_hash: str,
        page_range: tuple[int, int] | None,
    ) -> str:
        """
        Build deterministic output file name.
        """

        if page_range:

            scope = (
                f"pages_"
                f"{page_range[0]}_"
                f"{page_range[1]}"
            )

        else:

            scope = "full"

        return (
            f"{input_file.stem}_"
            f"{scope}_"
            f"{document_hash[:12]}"
        )

    # =========================================================
    # SUMMARY LOGGER
    # =========================================================

    def _log_summary(
        self,
        document: dict[str, Any],
    ) -> None:
        """
        Log canonical document summary.
        """

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
            if block.get(
                "type"
            ) == "table"
        )

        heading_count = sum(
            1
            for page in pages
            for block in page.get(
                "blocks",
                [],
            )
            if block.get(
                "type"
            ) == "heading"
        )

        text_count = sum(
            1
            for page in pages
            for block in page.get(
                "blocks",
                [],
            )
            if block.get(
                "type"
            ) == "text"
        )

        chart_count = sum(
            1
            for page in pages
            for block in page.get(
                "blocks",
                [],
            )
            if block.get(
                "type"
            ) == "chart"
        )

        diagram_count = sum(
            1
            for page in pages
            for block in page.get(
                "blocks",
                [],
            )
            if block.get(
                "type"
            ) == "diagram"
        )

        image_count = sum(
            1
            for page in pages
            for block in page.get(
                "blocks",
                [],
            )
            if block.get(
                "type"
            ) == "image"
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
            "Pages: %s",
            len(pages),
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
# COMMAND LINE ARGUMENTS
# =============================================================


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.
    """

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
            "Reprocess even if the same document "
            "scope and parser version already "
            "exists in the registry."
        ),
    )

    return parser.parse_args()


# =============================================================
# MAIN ENTRY POINT
# =============================================================


def main() -> None:
    """
    CLI entry point.

    Main intentionally contains no parsing logic.
    It only:
    - accepts input
    - creates ParsingComponent
    - executes the component
    """

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

        # Detailed error is already written
        # into the run log.
        sys.exit(1)


if __name__ == "__main__":
    main()