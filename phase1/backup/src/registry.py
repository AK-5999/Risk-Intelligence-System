from __future__ import annotations

import json

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ProcessingRegistry:
    """
    JSON-based registry for the current POC.

    It tracks:
    - Document hash
    - Parser version
    - Processing scope
    - Processing status
    - Output paths
    - OCR candidate pages
    - Basic extraction summary

    Limitation:
    This registry is designed for local sequential execution.
    It is not safe for parallel workers.
    """

    def __init__(self, registry_path: Path) -> None:
        self.registry_path = registry_path

        self.registry_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    def load(self) -> dict[str, Any]:
        """Load the complete registry."""

        if not self.registry_path.exists():
            return {}

        try:
            with self.registry_path.open(
                mode="r",
                encoding="utf-8",
            ) as registry_file:
                data = json.load(registry_file)

        except json.JSONDecodeError as error:
            raise ValueError(
                f"Registry contains invalid JSON: "
                f"{self.registry_path}"
            ) from error

        if not isinstance(data, dict):
            raise ValueError(
                "Registry root must be a JSON object."
            )

        return data

    def save(self, data: dict[str, Any]) -> None:
        """Save the registry using a temporary file."""

        temporary_path = self.registry_path.with_suffix(
            self.registry_path.suffix + ".tmp"
        )

        with temporary_path.open(
            mode="w",
            encoding="utf-8",
        ) as registry_file:
            json.dump(
                data,
                registry_file,
                indent=2,
                ensure_ascii=False,
                default=str,
            )

        temporary_path.replace(self.registry_path)

    @staticmethod
    def build_key(
        document_hash: str,
        page_range: tuple[int, int] | None,
        parser_name: str,
        parser_version: str,
    ) -> str:
        """Build a unique processing-registry key."""

        if page_range is None:
            scope = "full"
        else:
            start_page, end_page = page_range

            if start_page < 1:
                raise ValueError(
                    "Page range start must be at least 1."
                )

            if end_page < start_page:
                raise ValueError(
                    "Page range end cannot be smaller than start."
                )

            scope = f"pages-{start_page}-{end_page}"

        return (
            f"{document_hash}:"
            f"{scope}:"
            f"{parser_name}:"
            f"{parser_version}"
        )

    def get(
        self,
        registry_key: str,
    ) -> dict[str, Any] | None:
        """Return an existing record."""

        registry = self.load()
        record = registry.get(registry_key)

        return record if isinstance(record, dict) else None

    def is_completed(
        self,
        registry_key: str,
        verify_output: bool = True,
    ) -> bool:
        """Check whether processing has already completed."""

        record = self.get(registry_key)

        if record is None:
            return False

        if record.get("status") != "completed":
            return False

        if not verify_output:
            return True

        output_json = record.get("output_json")

        if not output_json:
            return False

        return Path(output_json).exists()

    def mark_processing(
        self,
        registry_key: str,
        document_hash: str,
        file_path: Path,
        output_json: Path,
        output_markdown: Path,
        page_range: tuple[int, int] | None,
        parser_name: str,
        parser_version: str,
    ) -> None:
        """Mark the document as currently processing."""

        record = {
            "document_hash": document_hash,
            "file_name": file_path.name,
            "source_path": str(file_path.resolve()),
            "page_range": (
                list(page_range)
                if page_range
                else None
            ),
            "parser_name": parser_name,
            "parser_version": parser_version,
            "output_json": str(output_json.resolve()),
            "output_markdown": str(
                output_markdown.resolve()
            ),
            "status": "processing",
            "processing_started_at": self._timestamp(),
            "processing_completed_at": None,
            "error": None,
        }

        self.add_or_update(
            registry_key=registry_key,
            record=record,
        )

    def mark_completed(
        self,
        registry_key: str,
        result: dict[str, Any],
        output_json: Path,
        output_markdown: Path,
    ) -> None:
        """Mark processing as completed."""

        existing = self.get(registry_key) or {}

        quality = result.get("quality", {})
        summary = result.get("content_summary", {})
        processing = result.get("processing", {})

        record = {
            **existing,
            "document_id": result.get("document_id"),
            "status": "completed",
            "parser_status": processing.get("status"),
            "output_json": str(output_json.resolve()),
            "output_markdown": str(
                output_markdown.resolve()
            ),
            "pages_processed": quality.get(
                "pages_processed",
                0,
            ),
            "pages_with_text": quality.get(
                "pages_with_text",
                0,
            ),
            "pages_with_tables": quality.get(
                "pages_with_tables",
                0,
            ),
            "pages_with_pictures": quality.get(
                "pages_with_pictures",
                0,
            ),
            "pages_requiring_ocr": quality.get(
                "pages_requiring_ocr",
                0,
            ),
            "ocr_pages_processed": quality.get(
                "ocr_pages_processed",
                0,
            ),
            "total_blocks": summary.get(
                "total_blocks",
                0,
            ),
            "total_tables": summary.get(
                "total_tables",
                0,
            ),
            "total_pictures": summary.get(
                "total_pictures",
                0,
            ),
            "page_type_counts": summary.get(
                "page_type_counts",
                {},
            ),
            "ocr_required_pages": summary.get(
                "ocr_required_pages",
                [],
            ),
            "processing_completed_at": self._timestamp(),
            "error": None,
        }

        self.add_or_update(
            registry_key=registry_key,
            record=record,
        )

    def mark_failed(
        self,
        registry_key: str,
        error: Exception | str,
        result: dict[str, Any] | None = None,
    ) -> None:
        """Mark processing as failed."""

        existing = self.get(registry_key) or {}

        if isinstance(error, Exception):
            error_type = type(error).__name__
            message = str(error)
        else:
            error_type = "ProcessingError"
            message = str(error)

        error_data: dict[str, Any] = {
            "error_type": error_type,
            "message": message,
        }

        if result and result.get("errors"):
            error_data["details"] = result["errors"]

        record = {
            **existing,
            "status": "failed",
            "processing_completed_at": self._timestamp(),
            "error": error_data,
        }

        self.add_or_update(
            registry_key=registry_key,
            record=record,
        )

    def add_or_update(
        self,
        registry_key: str,
        record: dict[str, Any],
    ) -> None:
        """Insert or replace a registry record."""

        registry = self.load()
        registry[registry_key] = record
        self.save(registry)

    @staticmethod
    def _timestamp() -> str:
        """Return a timezone-aware UTC timestamp."""

        return datetime.now(timezone.utc).isoformat()