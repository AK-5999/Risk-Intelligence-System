from __future__ import annotations

import argparse
import logging
import sys

from datetime import datetime
from pathlib import Path
from typing import Any

import torch

from pdf_parser import PDFParser
from registry import ProcessingRegistry


class ParsingComponent:
    """
    Modular document parsing component.

    Responsibilities:
    - Resolve project-relative paths
    - Initialize the PDF parser
    - Initialize processing registry
    - Detect duplicate processing
    - Execute parsing
    - Save JSON and Markdown outputs
    - Maintain run-specific logs
    - Update processing registry

    Currently supported:
    - PDF documents

    Future scope:
    - DOCX
    - PPTX
    - XLSX
    """

    def __init__(
        self,
        force_reprocess: bool = False,
    ) -> None:

        # ---------------------------------------------------------
        # PROJECT PATHS
        # ---------------------------------------------------------

        # Current file:
        # phase1/src/parser_main.py
        src_dir = Path(__file__).resolve().parent

        # phase1/
        self.phase1_dir = src_dir.parent

        # Output locations
        self.output_dir = self.phase1_dir / "output"

        self.json_output_dir = (
            self.output_dir / "processed_json"
        )

        self.markdown_output_dir = (
            self.output_dir / "processed_md"
        )

        # Registry location
        self.registry_dir = (
            self.phase1_dir / "registry_report"
        )

        # Logger location
        self.logger_dir = (
            self.phase1_dir / "logger"
        )

        self._create_directories()

        # ---------------------------------------------------------
        # RUN LOGGER
        # ---------------------------------------------------------

        self.log_path = self._configure_logger()

        # ---------------------------------------------------------
        # REGISTRY
        # ---------------------------------------------------------

        self.registry = ProcessingRegistry(
            registry_path=(
                self.registry_dir
                / "processed_files.json"
            )
        )

        # ---------------------------------------------------------
        # PARSER
        # ---------------------------------------------------------

        self.parser = PDFParser(
            enable_table_structure=True,
            enable_picture_classification=True,
            enable_chart_extraction=True,
            generate_picture_images=True,
            images_scale=2.0,
            minimum_native_text_characters=20,
        )

        self.force_reprocess = force_reprocess

    # =============================================================
    # SETUP
    # =============================================================

    def _create_directories(self) -> None:
        """
        Create all component directories automatically.
        """

        directories = [
            self.json_output_dir,
            self.markdown_output_dir,
            self.registry_dir,
            self.logger_dir,
        ]

        for directory in directories:
            directory.mkdir(
                parents=True,
                exist_ok=True,
            )

    def _configure_logger(self) -> Path:
        """
        Create a new log file for every execution.

        Example:
        logger/run_20260807_105501_123456.txt
        """

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        log_path = (
            self.logger_dir
            / f"run_{timestamp}.txt"
        )

        logger = logging.getLogger(
            "parsing_component"
        )

        logger.setLevel(logging.INFO)

        # Important if component is instantiated
        # multiple times in same Python process.
        logger.handlers.clear()

        file_handler = logging.FileHandler(
            log_path,
            mode="w",
            encoding="utf-8",
        )

        formatter = logging.Formatter(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

        self.logger = logger

        return log_path

    # =============================================================
    # PUBLIC PROCESSING API
    # =============================================================

    def process(
        self,
        input_file: str | Path,
        page_range: tuple[int, int] | None = None,
    ) -> dict[str, Any] | None:
        """
        Parse one document.

        Parameters
        ----------
        input_file:
            Absolute or relative path to input PDF.

        page_range:
            Optional 1-based page range.

            Example:
                (71, 74)

            None:
                Process complete document.

        Returns
        -------
        dict | None
            Parsed document result.

            None is returned when processing
            is skipped because the same document
            was already completed.
        """

        input_file = Path(input_file).expanduser().resolve()

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
            "Processing scope: %s",
            (
                page_range
                if page_range
                else "complete document"
            ),
        )

        self.logger.info(
            "Force reprocess: %s",
            self.force_reprocess,
        )

        try:

            # -----------------------------------------------------
            # VALIDATION
            # -----------------------------------------------------

            self._validate_input(
                input_file
            )

            # -----------------------------------------------------
            # ENVIRONMENT
            # -----------------------------------------------------

            self._log_environment()

            # -----------------------------------------------------
            # HASH
            # -----------------------------------------------------

            self.logger.info(
                "Calculating SHA-256 hash..."
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

            # -----------------------------------------------------
            # REGISTRY KEY
            # -----------------------------------------------------

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

            # -----------------------------------------------------
            # OUTPUT PATHS
            # -----------------------------------------------------

            output_json, output_markdown = (
                self._build_output_paths(
                    input_file=input_file,
                    document_hash=document_hash,
                    page_range=page_range,
                )
            )

            self.logger.info(
                "JSON output: %s",
                output_json,
            )

            self.logger.info(
                "Markdown output: %s",
                output_markdown,
            )

            self.logger.info(
                "Registry: %s",
                self.registry.registry_path,
            )

            # -----------------------------------------------------
            # DUPLICATE PROCESSING CHECK
            # -----------------------------------------------------

            if self._should_skip(
                registry_key
            ):
                existing = self.registry.get(
                    registry_key
                )

                self.logger.info(
                    "Processing skipped."
                )

                self.logger.info(
                    "Reason: same document, "
                    "scope and parser version "
                    "already completed."
                )

                if existing:
                    self.logger.info(
                        "Existing JSON output: %s",
                        existing.get(
                            "output_json"
                        ),
                    )

                return None

            # -----------------------------------------------------
            # REGISTRY -> PROCESSING
            # -----------------------------------------------------

            self.registry.mark_processing(
                registry_key=registry_key,
                document_hash=document_hash,
                file_path=input_file,
                output_json=output_json,
                output_markdown=output_markdown,
                page_range=page_range,
                parser_name=(
                    self.parser.PARSER_NAME
                ),
                parser_version=(
                    self.parser.PARSER_VERSION
                ),
            )

            # -----------------------------------------------------
            # INSPECTION
            # -----------------------------------------------------

            inspection = self.parser.inspect(
                input_file
            )

            self.logger.info(
                "Input inspection completed."
            )

            self.logger.info(
                "File size: %s bytes",
                inspection.get(
                    "file_size_bytes"
                ),
            )

            self.logger.info(
                "Source path: %s",
                inspection.get(
                    "source_path"
                ),
            )

            # -----------------------------------------------------
            # PARSING
            # -----------------------------------------------------

            self.logger.info(
                "Starting adaptive Docling "
                "PDF processing."
            )

            self.logger.info(
                "Pass 1: native text, tables, "
                "pictures, charts, diagrams "
                "and OCR candidate detection."
            )

            self.logger.info(
                "Pass 2: OCR is applied to "
                "identified OCR candidate pages."
            )

            result = self.parser.parse(
                file_path=input_file,
                document_hash=document_hash,
                page_range=page_range,
            )

            # -----------------------------------------------------
            # SAVE OUTPUTS
            # -----------------------------------------------------

            self.parser.save_json(
                data=result,
                output_path=output_json,
            )

            self.parser.save_markdown(
                markdown=result.get(
                    "markdown",
                    "",
                ),
                output_path=output_markdown,
            )

            parser_status = (
                result
                .get("processing", {})
                .get("status")
            )

            # -----------------------------------------------------
            # FAILED PARSER RESULT
            # -----------------------------------------------------

            if parser_status == "failed":

                self.registry.mark_failed(
                    registry_key=registry_key,
                    error=(
                        "Adaptive PDF "
                        "processing failed."
                    ),
                    result=result,
                )

                self.logger.error(
                    "Parser returned failed status."
                )

                for error in result.get(
                    "errors",
                    [],
                ):
                    self.logger.error(
                        "%s: %s",
                        error.get(
                            "error_type"
                        ),
                        error.get(
                            "message"
                        ),
                    )

                return result

            # -----------------------------------------------------
            # REGISTRY -> COMPLETED
            # -----------------------------------------------------

            self.registry.mark_completed(
                registry_key=registry_key,
                result=result,
                output_json=output_json,
                output_markdown=(
                    output_markdown
                ),
            )

            # -----------------------------------------------------
            # FINAL SUMMARY
            # -----------------------------------------------------

            self._log_result_summary(
                result=result,
                output_json=output_json,
                output_markdown=(
                    output_markdown
                ),
            )

            return result

        except KeyboardInterrupt:

            self.logger.warning(
                "Processing interrupted by user."
            )

            if registry_key:
                self.registry.mark_failed(
                    registry_key=registry_key,
                    error=(
                        "Processing interrupted "
                        "by user."
                    ),
                )

            raise

        except Exception as error:

            self.logger.exception(
                "Unexpected processing error: "
                "%s: %s",
                type(error).__name__,
                error,
            )

            if registry_key:
                self.registry.mark_failed(
                    registry_key=registry_key,
                    error=error,
                )

            raise

    # =============================================================
    # INTERNAL HELPERS
    # =============================================================

    def _validate_input(
        self,
        input_file: Path,
    ) -> None:

        if not input_file.exists():
            raise FileNotFoundError(
                f"Input file not found: "
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

    def _should_skip(
        self,
        registry_key: str,
    ) -> bool:

        if self.force_reprocess:
            return False

        return self.registry.is_completed(
            registry_key=registry_key,
            verify_output=True,
        )

    def _build_output_paths(
        self,
        input_file: Path,
        document_hash: str,
        page_range: tuple[int, int] | None,
    ) -> tuple[Path, Path]:

        if page_range is None:
            scope_name = "full"
        else:
            scope_name = (
                f"pages_"
                f"{page_range[0]}_"
                f"{page_range[1]}"
            )

        output_base_name = (
            f"{input_file.stem}_"
            f"{scope_name}_"
            f"{document_hash[:12]}"
        )

        output_json = (
            self.json_output_dir
            / f"{output_base_name}.json"
        )

        output_markdown = (
            self.markdown_output_dir
            / f"{output_base_name}.md"
        )

        return (
            output_json,
            output_markdown,
        )

    def _log_environment(self) -> None:

        cuda_available = (
            torch.cuda.is_available()
        )

        self.logger.info(
            "CUDA available: %s",
            cuda_available,
        )

        if cuda_available:

            self.logger.info(
                "GPU: %s",
                torch.cuda.get_device_name(0),
            )

            self.logger.info(
                "CUDA version: %s",
                torch.version.cuda,
            )

    def _log_result_summary(
        self,
        result: dict[str, Any],
        output_json: Path,
        output_markdown: Path,
    ) -> None:

        quality = result.get(
            "quality",
            {},
        )

        summary = result.get(
            "content_summary",
            {},
        )

        processing = result.get(
            "processing",
            {},
        )

        self.logger.info(
            "=" * 72
        )

        self.logger.info(
            "PROCESSING COMPLETED"
        )

        self.logger.info(
            "=" * 72
        )

        self.logger.info(
            "Status: %s",
            processing.get(
                "status"
            ),
        )

        self.logger.info(
            "Strategy: %s",
            processing.get(
                "strategy"
            ),
        )

        self.logger.info(
            "Pages processed: %s",
            quality.get(
                "pages_processed",
                0,
            ),
        )

        self.logger.info(
            "Pages with text: %s",
            quality.get(
                "pages_with_text",
                0,
            ),
        )

        self.logger.info(
            "Pages with tables: %s",
            quality.get(
                "pages_with_tables",
                0,
            ),
        )

        self.logger.info(
            "Pages with pictures: %s",
            quality.get(
                "pages_with_pictures",
                0,
            ),
        )

        self.logger.info(
            "OCR candidate pages: %s",
            quality.get(
                "pages_requiring_ocr",
                0,
            ),
        )

        self.logger.info(
            "OCR pages processed: %s",
            quality.get(
                "ocr_pages_processed",
                0,
            ),
        )

        self.logger.info(
            "Total blocks: %s",
            summary.get(
                "total_blocks",
                0,
            ),
        )

        self.logger.info(
            "Total tables: %s",
            summary.get(
                "total_tables",
                0,
            ),
        )

        self.logger.info(
            "Total pictures: %s",
            summary.get(
                "total_pictures",
                0,
            ),
        )

        self.logger.info(
            "Quality score: %s",
            quality.get(
                "overall_quality_score"
            ),
        )

        self.logger.info(
            "OCR required pages: %s",
            summary.get(
                "ocr_required_pages",
                [],
            ),
        )

        page_type_counts = summary.get(
            "page_type_counts",
            {},
        )

        for page_type, count in sorted(
            page_type_counts.items()
        ):
            self.logger.info(
                "Page type [%s]: %s",
                page_type,
                count,
            )

        label_counts = summary.get(
            "label_counts",
            {},
        )

        for label, count in sorted(
            label_counts.items()
        ):
            self.logger.info(
                "Block type [%s]: %s",
                label,
                count,
            )

        for warning in result.get(
            "warnings",
            [],
        ):
            self.logger.warning(
                "%s",
                warning,
            )

        self.logger.info(
            "JSON output: %s",
            output_json,
        )

        self.logger.info(
            "Markdown output: %s",
            output_markdown,
        )

        self.logger.info(
            "Registry: %s",
            self.registry.registry_path,
        )

        self.logger.info(
            "Run log: %s",
            self.log_path,
        )


# =============================================================
# CLI
# =============================================================


def parse_arguments() -> argparse.Namespace:
    """
    Command-line interface for the parsing component.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Risk Intelligence System - "
            "Document Parsing Component"
        )
    )

    parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=str,
        help="Path to input PDF document.",
    )

    parser.add_argument(
        "--pages",
        nargs=2,
        type=int,
        metavar=("START", "END"),
        help=(
            "Optional 1-based page range. "
            "Example: --pages 71 74. "
            "If omitted, complete PDF "
            "is processed."
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Reprocess document even if "
            "registry already marks it "
            "as completed."
        ),
    )

    return parser.parse_args()


def main() -> None:

    args = parse_arguments()

    page_range = (
        tuple(args.pages)
        if args.pages
        else None
    )

    component = ParsingComponent(
        force_reprocess=args.force,
    )

    try:

        component.process(
            input_file=args.input,
            page_range=page_range,
        )

    except KeyboardInterrupt:
        sys.exit(130)

    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()


#uv run parser_main.py \
#  --input "D:\Coding\Vestas\Pipeline\data\VestasAnnualReport2025.pdf" \
#  --pages 71 74 \
#  --force