from __future__ import annotations

import json

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ProcessingRegistry:
    """
    Document-centric JSON processing registry
    for the Phase 1 POC.

    Design:
        One source PDF
            ↓
        One document hash
            ↓
        One registry record
            ↓
        Multiple processed pages can accumulate

    Registry tracks:
    - Stable document identity
    - Parser name/version
    - Source file
    - Processed pages
    - Current/latest requested pages
    - Processing status
    - Raw JSON path
    - Canonical JSON path
    - Aggregated extraction summary
    - Errors

    Important:
    Page range is NOT part of the registry identity.

    Example:

        First run:
            pages 50-51

        Second run:
            pages 71-74

        Registry remains ONE record:

            processed_pages:
            [50, 51, 71, 72, 73, 74]

    Limitation:
    This local JSON registry is intended for
    sequential POC execution.

    It is not concurrency-safe for multiple
    parallel workers.
    """

    def __init__(
        self,
        registry_path: Path,
    ) -> None:

        self.registry_path = (
            Path(registry_path)
            .resolve()
        )

        self.registry_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Always initialize a valid JSON registry.
        if not self.registry_path.exists():

            self.save({})

    # =========================================================
    # LOAD / SAVE
    # =========================================================

    def load(
        self,
    ) -> dict[str, Any]:
        """
        Load complete registry.

        Missing or empty registry behaves as {}.

        Non-empty malformed JSON raises an error.
        """

        if not self.registry_path.exists():
            return {}

        content = (
            self.registry_path
            .read_text(
                encoding="utf-8"
            )
            .strip()
        )

        if not content:
            return {}

        try:

            data = json.loads(
                content
            )

        except json.JSONDecodeError as error:

            raise ValueError(
                (
                    "Registry contains invalid JSON: "
                    f"{self.registry_path}"
                )
            ) from error

        if not isinstance(
            data,
            dict,
        ):

            raise ValueError(
                "Registry root must be a JSON object."
            )

        return data

    def save(
        self,
        data: dict[str, Any],
    ) -> None:
        """
        Save registry atomically.

        Temporary-file replacement prevents
        partially written registry files.
        """

        temporary_path = (
            self.registry_path
            .with_suffix(
                self.registry_path.suffix
                + ".tmp"
            )
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

        temporary_path.replace(
            self.registry_path
        )

    # =========================================================
    # DOCUMENT KEY
    # =========================================================

    @staticmethod
    def build_key(
        document_hash: str,
        page_range: tuple[int, int] | None,
        parser_name: str,
        parser_version: str,
    ) -> str:
        """
        Build stable document-level registry key.

        page_range is intentionally NOT included.

        It remains in this method signature only
        for compatibility with parser_main.py.

        Old:
            hash:pages-50-51:parser:version
            hash:pages-71-74:parser:version

        New:
            hash:parser:version
        """

        # Validate supplied page range even though
        # it is not part of the identity.
        if page_range is not None:

            start_page, end_page = (
                page_range
            )

            if start_page < 1:

                raise ValueError(
                    (
                        "Page range start must "
                        "be at least 1."
                    )
                )

            if end_page < start_page:

                raise ValueError(
                    (
                        "Page range end cannot "
                        "be smaller than start."
                    )
                )

        return (
            f"{document_hash}:"
            f"{parser_name}:"
            f"{parser_version}"
        )

    # =========================================================
    # GET
    # =========================================================

    def get(
        self,
        registry_key: str,
    ) -> dict[str, Any] | None:
        """
        Get one document registry record.
        """

        registry = self.load()

        record = registry.get(
            registry_key
        )

        if isinstance(
            record,
            dict,
        ):
            return record

        return None

    # =========================================================
    # PAGE CHECKING
    # =========================================================

    def has_pages(
        self,
        registry_key: str,
        page_range: tuple[int, int],
    ) -> bool:
        """
        Return True if all requested pages
        already exist in the registry.

        Example:

            processed_pages:
                [50, 51, 71, 72]

            requested:
                (50, 51)

            -> True

            requested:
                (50, 52)

            -> False
        """

        record = self.get(
            registry_key
        )

        if not record:
            return False

        processed_pages = {
            int(page)
            for page
            in record.get(
                "processed_pages",
                [],
            )
        }

        start_page, end_page = (
            page_range
        )

        requested_pages = set(
            range(
                start_page,
                end_page + 1,
            )
        )

        return (
            requested_pages
            .issubset(
                processed_pages
            )
        )

    def is_completed(
        self,
        registry_key: str,
        verify_output: bool = True,
    ) -> bool:
        """
        Check whether document has at least one
        successful completed processing state.

        This method is retained for compatibility.

        Page-level duplicate checking should now use:
            has_pages(...)
        or canonical JSON page inspection.
        """

        record = self.get(
            registry_key
        )

        if record is None:
            return False

        if (
            record.get("status")
            != "completed"
        ):
            return False

        if not verify_output:
            return True

        outputs = record.get(
            "outputs",
            {},
        )

        canonical_json = outputs.get(
            "canonical_json"
        )

        if not canonical_json:
            return False

        return Path(
            canonical_json
        ).exists()

    # =========================================================
    # MARK PROCESSING
    # =========================================================

    def mark_processing(
        self,
        registry_key: str,
        document_hash: str,
        file_path: Path,
        raw_output_json: Path,
        canonical_output_json: Path,
        page_range: tuple[int, int] | None,
        parser_name: str,
        parser_version: str,
    ) -> None:
        """
        Mark latest document operation as processing.

        Existing processed_pages are preserved.
        """

        existing = (
            self.get(
                registry_key
            )
            or {}
        )

        now = self._timestamp()

        requested_pages = (
            self._page_range_to_list(
                page_range
            )
        )

        existing_processed_pages = (
            self._normalize_page_list(
                existing.get(
                    "processed_pages",
                    [],
                )
            )
        )

        record = {
            **existing,

            "document_hash": (
                document_hash
            ),

            "file_name": (
                file_path.name
            ),

            "source_path": str(
                file_path.resolve()
            ),

            "parser": {
                "name": (
                    parser_name
                ),
                "version": (
                    parser_version
                ),
            },

            "outputs": {
                "raw_json": str(
                    raw_output_json.resolve()
                ),
                "canonical_json": str(
                    canonical_output_json.resolve()
                ),
            },

            # Pages successfully available from
            # previous runs remain untouched.
            "processed_pages": (
                existing_processed_pages
            ),

            "processed_page_count": (
                len(
                    existing_processed_pages
                )
            ),

            # Scope of THIS invocation only.
            "current_request": {
                "page_range": (
                    list(page_range)
                    if page_range
                    else None
                ),
                "requested_pages": (
                    requested_pages
                ),
                "force_reprocess": None,
            },

            "status": "processing",

            # Created once.
            "created_at": (
                existing.get(
                    "created_at"
                )
                or now
            ),

            # Start timestamp for latest run.
            "processing_started_at": (
                now
            ),

            "processing_completed_at": None,

            "last_successful_at": (
                existing.get(
                    "last_successful_at"
                )
            ),

            "error": None,
        }

        self.add_or_update(
            registry_key=registry_key,
            record=record,
        )

    # =========================================================
    # MARK COMPLETED
    # =========================================================

    def mark_completed(
        self,
        registry_key: str,
        result: dict[str, Any],
        raw_output_json: Path,
        canonical_output_json: Path,
    ) -> None:
        """
        Mark document operation as completed.

        Important:
        We derive final processed_pages from the
        merged canonical JSON, not just from the
        current parser result.

        Therefore:

            run 1 -> 50, 51

            run 2 -> 71, 72, 73, 74

        results in:

            processed_pages:
            [50, 51, 71, 72, 73, 74]
        """

        existing = (
            self.get(
                registry_key
            )
            or {}
        )

        # -----------------------------------------------------
        # LOAD FINAL MERGED CANONICAL OUTPUT
        # -----------------------------------------------------

        canonical_document = (
            self._load_json_file(
                canonical_output_json
            )
            or {}
        )

        # -----------------------------------------------------
        # LOAD FINAL MERGED RAW OUTPUT
        # -----------------------------------------------------

        raw_document = (
            self._load_json_file(
                raw_output_json
            )
            or result
        )

        # -----------------------------------------------------
        # FULL PROCESSED PAGE LIST
        # -----------------------------------------------------

        processed_pages = (
            self._extract_page_numbers(
                canonical_document
            )
        )

        # Fallback if canonical file somehow
        # does not contain pages.
        if not processed_pages:

            processed_pages = (
                self._extract_page_numbers(
                    raw_document
                )
            )

        processed_pages = (
            self._normalize_page_list(
                processed_pages
            )
        )

        # -----------------------------------------------------
        # DOCUMENT ID
        # -----------------------------------------------------

        document_id = (
            canonical_document.get(
                "document_id"
            )
            or existing.get(
                "document_id"
            )
            or result.get(
                "document_id"
            )
        )

        # -----------------------------------------------------
        # FINAL AGGREGATED SUMMARY
        # -----------------------------------------------------

        quality = raw_document.get(
            "quality",
            {},
        )

        summary = raw_document.get(
            "content_summary",
            {},
        )

        processing = result.get(
            "processing",
            {},
        )

        now = self._timestamp()

        record = {
            **existing,

            "document_id": (
                document_id
            ),

            "document_hash": (
                result.get(
                    "document_hash"
                )
                or existing.get(
                    "document_hash"
                )
            ),

            "status": "completed",

            "parser_status": (
                processing.get(
                    "status"
                )
            ),

            "outputs": {
                "raw_json": str(
                    raw_output_json.resolve()
                ),
                "canonical_json": str(
                    canonical_output_json.resolve()
                ),
            },

            # ---------------------------------------------
            # DOCUMENT-LEVEL PAGE STATE
            # ---------------------------------------------

            "processed_pages": (
                processed_pages
            ),

            "processed_page_count": (
                len(
                    processed_pages
                )
            ),

            # ---------------------------------------------
            # LATEST REQUEST
            # ---------------------------------------------

            "last_request": (
                existing.get(
                    "current_request"
                )
            ),

            "current_request": None,

            # ---------------------------------------------
            # AGGREGATED EXTRACTION SUMMARY
            # ---------------------------------------------

            "extraction_summary": {
                "pages_processed": (
                    len(
                        processed_pages
                    )
                ),

                "pages_with_text": (
                    quality.get(
                        "pages_with_text",
                        0,
                    )
                ),

                "pages_with_tables": (
                    quality.get(
                        "pages_with_tables",
                        0,
                    )
                ),

                "pages_with_pictures": (
                    quality.get(
                        "pages_with_pictures",
                        0,
                    )
                ),

                "pages_requiring_ocr": (
                    quality.get(
                        "pages_requiring_ocr",
                        0,
                    )
                ),

                "ocr_pages_processed": (
                    quality.get(
                        "ocr_pages_processed",
                        0,
                    )
                ),

                "empty_pages": (
                    quality.get(
                        "empty_pages",
                        0,
                    )
                ),

                "total_blocks": (
                    summary.get(
                        "total_blocks",
                        0,
                    )
                ),

                "total_tables": (
                    summary.get(
                        "total_tables",
                        0,
                    )
                ),

                "total_pictures": (
                    summary.get(
                        "total_pictures",
                        0,
                    )
                ),

                "label_counts": (
                    summary.get(
                        "label_counts",
                        {},
                    )
                ),

                "page_type_counts": (
                    summary.get(
                        "page_type_counts",
                        {},
                    )
                ),

                "ocr_required_pages": (
                    summary.get(
                        "ocr_required_pages",
                        [],
                    )
                ),
            },

            "processing_completed_at": (
                now
            ),

            "last_successful_at": (
                now
            ),

            "error": None,
        }

        self.add_or_update(
            registry_key=registry_key,
            record=record,
        )

    # =========================================================
    # MARK FAILED
    # =========================================================

    def mark_failed(
        self,
        registry_key: str,
        error: Exception | str,
        result: dict[str, Any] | None = None,
    ) -> None:
        """
        Mark latest processing attempt as failed.

        Previously processed pages remain preserved.
        """

        existing = (
            self.get(
                registry_key
            )
            or {}
        )

        if isinstance(
            error,
            Exception,
        ):

            error_type = (
                type(error).__name__
            )

            message = str(
                error
            )

        else:

            error_type = (
                "ProcessingError"
            )

            message = str(
                error
            )

        error_data: dict[str, Any] = {
            "error_type": (
                error_type
            ),
            "message": (
                message
            ),
        }

        if (
            result
            and result.get(
                "errors"
            )
        ):

            error_data[
                "details"
            ] = result[
                "errors"
            ]

        record = {
            **existing,

            "status": "failed",

            "last_request": (
                existing.get(
                    "current_request"
                )
            ),

            "current_request": None,

            "processing_completed_at": (
                self._timestamp()
            ),

            "error": (
                error_data
            ),
        }

        self.add_or_update(
            registry_key=registry_key,
            record=record,
        )

    # =========================================================
    # ADD / UPDATE
    # =========================================================

    def add_or_update(
        self,
        registry_key: str,
        record: dict[str, Any],
    ) -> None:
        """
        Insert or replace one document-level record.
        """

        registry = self.load()

        registry[
            registry_key
        ] = record

        self.save(
            registry
        )

    # =========================================================
    # JSON FILE HELPER
    # =========================================================

    @staticmethod
    def _load_json_file(
        file_path: Path,
    ) -> dict[str, Any] | None:
        """
        Load one JSON artifact safely.
        """

        if not file_path.exists():
            return None

        content = (
            file_path
            .read_text(
                encoding="utf-8"
            )
            .strip()
        )

        if not content:
            return None

        try:

            data = json.loads(
                content
            )

        except json.JSONDecodeError as error:

            raise ValueError(
                (
                    "Invalid JSON artifact: "
                    f"{file_path}"
                )
            ) from error

        if not isinstance(
            data,
            dict,
        ):

            raise ValueError(
                (
                    "JSON artifact root must "
                    f"be an object: {file_path}"
                )
            )

        return data

    # =========================================================
    # PAGE HELPERS
    # =========================================================

    @staticmethod
    def _page_range_to_list(
        page_range: tuple[int, int] | None,
    ) -> list[int] | None:
        """
        Convert page range into page numbers.

        (50, 51)
            ->
        [50, 51]
        """

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

    @staticmethod
    def _extract_page_numbers(
        document: dict[str, Any],
    ) -> list[int]:
        """
        Extract page numbers from canonical/raw
        document page collection.
        """

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

            try:

                page_numbers.append(
                    int(page_number)
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

        return sorted(
            set(
                page_numbers
            )
        )

    @staticmethod
    def _normalize_page_list(
        pages: list[Any],
    ) -> list[int]:
        """
        Convert page collection into unique
        sorted integer page numbers.
        """

        result = set()

        for page in pages:

            try:

                result.add(
                    int(page)
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

        return sorted(
            result
        )

    # =========================================================
    # TIMESTAMP
    # =========================================================

    @staticmethod
    def _timestamp() -> str:
        """
        Return timezone-aware UTC timestamp.
        """

        return (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        )