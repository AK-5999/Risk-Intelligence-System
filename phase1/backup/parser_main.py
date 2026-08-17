from __future__ import annotations

import sys

from pathlib import Path

from pdf_parser import PDFParser
from registry import ProcessingRegistry
import torch


def main() -> None:
    # ---------------------------------------------------------
    # INPUT CONFIGURATION
    # ---------------------------------------------------------
    
    input_file = Path(
        r"D:\Coding\Vestas\Pipeline\data"
        r"\VestasAnnualReport2025.pdf"
    )

    output_dir = Path(
        r"D:\Coding\Vestas\Pipeline"
        r"\phase\phase1\output"
    )

    # None means process the complete PDF.
    #
    # Example for only page 9:
    # page_range = (9, 9)
    page_range: tuple[int, int] | None = (71,71)

    # True means run again even when the same document and parser
    # version are already marked completed.
    force_reprocess = False

    # ---------------------------------------------------------
    # SETUP
    # ---------------------------------------------------------

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    registry = ProcessingRegistry(
        registry_path=(
            output_dir
            / "processed_files.json"
        )
    )

    parser = PDFParser(
        enable_table_structure=True,
        enable_picture_classification=True,
        enable_chart_extraction=True,
        generate_picture_images=True,
        images_scale=2.0,
        minimum_native_text_characters=20,
    )

    if not parser.can_parse(input_file):
        print(
            f"Unsupported or invalid PDF: "
            f"{input_file}"
        )
        sys.exit(1)

    registry_key: str | None = None

    try:
        if torch.cuda.is_available():
            print("GPU :", torch.cuda.get_device_name(0), ", CUDA Version :", torch.version.cuda)

        print("=" * 72)
        print("ADAPTIVE DOCLING PDF PARSER")
        print("=" * 72)

        print(f"Input file: {input_file}")
        print(
            "Processing scope: "
            f"{page_range or 'complete document'}"
        )

        print()
        print("Calculating SHA-256 hash...")

        document_hash = parser.calculate_hash(
            input_file
        )

        print(f"Document hash: {document_hash}")

        registry_key = registry.build_key(
            document_hash=document_hash,
            page_range=page_range,
            parser_name=parser.PARSER_NAME,
            parser_version=parser.PARSER_VERSION,
        )

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
            output_dir
            / f"{output_base_name}.json"
        )

        output_markdown = (
            output_dir
            / f"{output_base_name}.md"
        )

        if (
            not force_reprocess
            and registry.is_completed(
                registry_key=registry_key,
                verify_output=True,
            )
        ):
            existing = registry.get(
                registry_key
            )

            print()
            print(
                "The same document has already been "
                "processed with this parser version."
            )
            print("Processing skipped.")

            if existing:
                print(
                    "Existing output: "
                    f"{existing.get('output_json')}"
                )

            return

        registry.mark_processing(
            registry_key=registry_key,
            document_hash=document_hash,
            file_path=input_file,
            output_json=output_json,
            output_markdown=output_markdown,
            page_range=page_range,
            parser_name=parser.PARSER_NAME,
            parser_version=parser.PARSER_VERSION,
        )

        inspection = parser.inspect(input_file)

        print()
        print("Input inspection:")
        print(
            "  File size: "
            f"{inspection['file_size_bytes']} bytes"
        )
        print(
            f"  Source: "
            f"{inspection['source_path']}"
        )

        print()
        print(
            "Pass 1: detecting native text, tables, "
            "pictures, charts, diagrams and OCR candidates..."
        )

        print(
            "Pass 2 will automatically run OCR only "
            "on pages identified as OCR candidates."
        )

        result = parser.parse(
            file_path=input_file,
            document_hash=document_hash,
            page_range=page_range,
        )

        parser.save_json(
            data=result,
            output_path=output_json,
        )

        parser.save_markdown(
            markdown=result.get(
                "markdown",
                "",
            ),
            output_path=output_markdown,
        )

        parser_status = result[
            "processing"
        ]["status"]

        if parser_status == "failed":
            registry.mark_failed(
                registry_key=registry_key,
                error=(
                    "Adaptive PDF processing failed."
                ),
                result=result,
            )

            print()
            print("Processing failed.")

            for error in result["errors"]:
                print(
                    f"{error['error_type']}: "
                    f"{error['message']}"
                )

            print(
                f"Failure output: {output_json}"
            )

            sys.exit(1)

        registry.mark_completed(
            registry_key=registry_key,
            result=result,
            output_json=output_json,
            output_markdown=output_markdown,
        )

        quality = result["quality"]
        summary = result["content_summary"]
        processing = result["processing"]

        print()
        print("=" * 72)
        print("PROCESSING COMPLETED")
        print("=" * 72)

        print(f"Status: {parser_status}")
        print(
            "Strategy: "
            f"{processing['strategy']}"
        )
        print(
            "Pages processed: "
            f"{quality['pages_processed']}"
        )
        print(
            "Pages with text: "
            f"{quality['pages_with_text']}"
        )
        print(
            "Pages with tables: "
            f"{quality['pages_with_tables']}"
        )
        print(
            "Pages with pictures: "
            f"{quality['pages_with_pictures']}"
        )
        print(
            "OCR candidate pages: "
            f"{quality['pages_requiring_ocr']}"
        )
        print(
            "OCR pages successfully processed: "
            f"{quality['ocr_pages_processed']}"
        )
        print(
            "Total blocks: "
            f"{summary['total_blocks']}"
        )
        print(
            "Total tables: "
            f"{summary['total_tables']}"
        )
        print(
            "Total pictures: "
            f"{summary['total_pictures']}"
        )
        print(
            "Quality score: "
            f"{quality['overall_quality_score']}"
        )

        print()
        print(
            "OCR candidate page numbers: "
            f"{summary['ocr_required_pages']}"
        )

        print()
        print("Page classifications:")

        for page_type, count in sorted(
            summary[
                "page_type_counts"
            ].items()
        ):
            print(
                f"  {page_type}: {count}"
            )

        print()
        print("Detected block types:")

        for label, count in sorted(
            summary["label_counts"].items()
        ):
            print(f"  {label}: {count}")

        print()
        print(f"JSON output: {output_json}")
        print(
            f"Markdown output: {output_markdown}"
        )
        print(
            f"Registry: "
            f"{registry.registry_path}"
        )

        if result["warnings"]:
            print()
            print("Warnings:")

            for warning in result["warnings"]:
                print(f"  - {warning}")

    except KeyboardInterrupt:
        print()
        print("Processing interrupted by user.")

        if registry_key:
            registry.mark_failed(
                registry_key=registry_key,
                error="Processing interrupted by user.",
            )

        sys.exit(1)

    except Exception as error:
        print()
        print(
            f"Unexpected error: "
            f"{type(error).__name__}: {error}"
        )

        if registry_key:
            registry.mark_failed(
                registry_key=registry_key,
                error=error,
            )

        sys.exit(1)


if __name__ == "__main__":
    main()