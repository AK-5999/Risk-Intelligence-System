from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class DocumentParser(ABC):

    @abstractmethod
    def can_parse(
        self,
        file_path: Path,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def calculate_hash(
        self,
        file_path: Path,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def parse(
        self,
        file_path: Path,
        document_hash: str,
        page_range: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError