from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class BlockType(str, Enum):
    TEXT = "text"
    HEADING = "heading"
    TABLE = "table"
    FIGURE = "figure"
    CHART = "chart"
    DIAGRAM = "diagram"
    IMAGE = "image"
    UNKNOWN = "unknown"


@dataclass
class BoundingBox:
    left: float
    top: float
    right: float
    bottom: float
    coordinate_origin: str = "BOTTOMLEFT"

    @property
    def width(self) -> float:
        return abs(self.right - self.left)

    @property
    def height(self) -> float:
        return abs(self.top - self.bottom)

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass
class Provenance:
    page_number: int
    bbox: BoundingBox | None = None
    character_start: int | None = None
    character_end: int | None = None


@dataclass
class TableData:
    columns: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    row_count: int = 0
    column_count: int = 0

    # True when table structure required normalization.
    normalized: bool = False

    # Headers inferred from nearby page elements.
    inferred_headers: bool = False

    normalization_notes: list[str] = field(
        default_factory=list
    )


@dataclass
class ContentBlock:
    block_id: str

    page_number: int

    type: BlockType

    text: str = ""

    provenance: list[Provenance] = field(
        default_factory=list
    )

    table: TableData | None = None

    extraction_method: str | None = None

    classification: str | None = None

    confidence: float | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass
class PageData:
    page_number: int

    page_type: str | None = None

    blocks: list[ContentBlock] = field(
        default_factory=list
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass
class DocumentSource:
    file_name: str
    file_type: str
    file_size_bytes: int | None = None
    source_path: str | None = None


@dataclass
class CanonicalDocument:
    document_id: str

    document_hash: str

    source: DocumentSource

    pages: list[PageData]

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    parser: dict[str, Any] = field(
        default_factory=dict
    )

    normalization: dict[str, Any] = field(
        default_factory=dict
    )

    warnings: list[str] = field(
        default_factory=list
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)