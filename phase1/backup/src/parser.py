from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class DocumentParser(ABC):
    """
    Common contract for document parsers.

    Future parsers such as WordParser, PPTParser and ExcelParser
    should implement the same methods.
    """

    @abstractmethod
    def can_parse(self, file_path: Path) -> bool:
        """Return True when this parser supports the file."""
        raise NotImplementedError

    @abstractmethod
    def inspect(self, file_path: Path) -> dict[str, Any]:
        """Return lightweight document metadata."""
        raise NotImplementedError

    @abstractmethod
    def calculate_hash(self, file_path: Path) -> str:
        """Calculate a content-based hash for duplicate detection."""
        raise NotImplementedError

    @abstractmethod
    def parse(
        self,
        file_path: Path,
        document_hash: str | None = None,
        page_range: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        """
        Convert the document into the standard internal schema.

        page_range:
            None    -> process complete document
            (9, 9)  -> process only page 9
            (1, 10) -> process pages 1 to 10
        """
        raise NotImplementedError

    @abstractmethod
    def save_json(
        self,
        data: dict[str, Any],
        output_path: Path,
    ) -> None:
        """Save parser output as JSON."""
        raise NotImplementedError