from __future__ import annotations

import re

from models import (
    BlockType,
    ContentBlock,
    TableData,
)

from normalization.text_normalizer import (
    TextNormalizer,
)


class TableNormalizer:
    """
    Normalizes extracted table structures.

    Responsibilities:
    - clean cell text
    - detect generic/missing headers
    - associate nearby headings with table columns
    - preserve original table values
    """

    GENERIC_HEADER_PATTERN = re.compile(
        r"^\d+$"
    )

    def __init__(
        self,
        text_normalizer: TextNormalizer,
    ) -> None:

        self.text_normalizer = (
            text_normalizer
        )

    def normalize(
        self,
        table_block: ContentBlock,
        page_blocks: list[ContentBlock],
    ) -> ContentBlock:

        if table_block.table is None:
            return table_block

        table = table_block.table

        self._clean_table_content(
            table
        )

        if self._has_generic_headers(
            table.columns
        ):
            inferred_headers = (
                self._infer_headers_from_page(
                    table_block=table_block,
                    page_blocks=page_blocks,
                    expected_columns=(
                        table.column_count
                    ),
                )
            )

            if inferred_headers:

                table.columns = (
                    inferred_headers
                )

                table.inferred_headers = True

                table.normalized = True

                table.normalization_notes.append(
                    "Semantic headers inferred "
                    "from headings located above "
                    "the table."
                )

        return table_block

    def _clean_table_content(
        self,
        table: TableData,
    ) -> None:

        table.columns = [
            self.text_normalizer.normalize(
                column
            )
            for column in table.columns
        ]

        clean_rows: list[list[str]] = []

        for row in table.rows:

            clean_row = [
                self.text_normalizer.normalize(
                    cell
                )
                for cell in row
            ]

            clean_rows.append(
                clean_row
            )

        table.rows = clean_rows

    def _has_generic_headers(
        self,
        columns: list[str],
    ) -> bool:

        if not columns:
            return True

        generic_count = 0

        for column in columns:

            value = column.strip()

            if (
                not value
                or
                self.GENERIC_HEADER_PATTERN.match(
                    value
                )
            ):
                generic_count += 1

        return (
            generic_count
            == len(columns)
        )

    def _infer_headers_from_page(
        self,
        table_block: ContentBlock,
        page_blocks: list[ContentBlock],
        expected_columns: int,
    ) -> list[str] | None:
        """
        Infer semantic table headers from nearby heading blocks.

        Example for page 51:

            Main risks

            Geopolitics and regulatory framework
            Project execution
            Cyber attacks

                        ↓

                4-column table

            Column 0:
                Description
                Potential impact
                How we manage it

            Columns 1-3:
                Geopolitics...
                Project execution
                Cyber attacks

        Expected normalized columns:

            [
                "attribute",
                "Geopolitics and regulatory framework",
                "Project execution",
                "Cyber attacks",
            ]
        """

        if expected_columns < 2:
            return None

        table_bbox = self._get_primary_bbox(
            table_block
        )

        if table_bbox is None:
            return None

        # ---------------------------------------------------------
        # TABLE GEOMETRY
        # ---------------------------------------------------------

        table_width = (
            table_bbox.right
            - table_bbox.left
        )

        if table_width <= 0:
            return None

        estimated_column_width = (
            table_width
            / expected_columns
        )

        # First column is assumed to contain row attributes:
        # Description / Potential impact / How we manage it.
        #
        # Semantic risk headings should therefore start
        # approximately from column 1 onward.
        first_data_column_x = (
            table_bbox.left
            + estimated_column_width
        )

        # ---------------------------------------------------------
        # FIND CANDIDATE HEADINGS
        # ---------------------------------------------------------

        candidate_headings: list[
            tuple[float, float, ContentBlock]
        ] = []

        for block in page_blocks:

            # Don't compare table with itself.
            if (
                block.block_id
                == table_block.block_id
            ):
                continue

            # Only headings are useful as candidate headers.
            if block.type != BlockType.HEADING:
                continue

            heading_text = block.text.strip()

            if not heading_text:
                continue

            bbox = self._get_primary_bbox(
                block
            )

            if bbox is None:
                continue

            # -----------------------------------------------------
            # VERTICAL RELATIONSHIP
            # -----------------------------------------------------
            #
            # BOTTOMLEFT coordinate system:
            # larger y means higher on the page.
            #
            # Heading should be close to and above the table.

            vertical_distance = (
                bbox.bottom
                - table_bbox.top
            )

            if not (
                -20
                <= vertical_distance
                <= 100
            ):
                continue

            # -----------------------------------------------------
            # HORIZONTAL RELATIONSHIP
            # -----------------------------------------------------

            heading_center_x = (
                bbox.left
                + bbox.right
            ) / 2

            # Ignore broad section headings positioned over
            # the first attribute column, e.g. "Main risks".
            if (
                heading_center_x
                < first_data_column_x
            ):
                continue

            candidate_headings.append(
                (
                    heading_center_x,
                    abs(vertical_distance),
                    block,
                )
            )

        # ---------------------------------------------------------
        # VALIDATE CANDIDATES
        # ---------------------------------------------------------

        required_heading_count = (
            expected_columns - 1
        )

        if (
            len(candidate_headings)
            < required_heading_count
        ):
            return None

        # ---------------------------------------------------------
        # SORT LEFT → RIGHT
        # ---------------------------------------------------------

        candidate_headings.sort(
            key=lambda item: item[0]
        )

        # If more headings are found than required,
        # choose headings that best align with expected
        # data-column centers.
        selected_headings: list[
            ContentBlock
        ] = []

        expected_centers = []

        for column_index in range(
            1,
            expected_columns,
        ):
            center_x = (
                table_bbox.left
                + (
                    column_index
                    + 0.5
                )
                * estimated_column_width
            )

            expected_centers.append(
                center_x
            )

        remaining_candidates = (
            candidate_headings.copy()
        )

        for expected_center in expected_centers:

            if not remaining_candidates:
                break

            best_candidate = min(
                remaining_candidates,
                key=lambda item: abs(
                    item[0]
                    - expected_center
                ),
            )

            selected_headings.append(
                best_candidate[2]
            )

            remaining_candidates.remove(
                best_candidate
            )

        if (
            len(selected_headings)
            != required_heading_count
        ):
            return None

        # Ensure final semantic order follows
        # the actual PDF left-to-right layout.
        selected_headings.sort(
            key=lambda block: (
                (
                    self._get_primary_bbox(
                        block
                    ).left
                    +
                    self._get_primary_bbox(
                        block
                    ).right
                )
                / 2
            )
        )

        headings = [
            block.text.strip()
            for block
            in selected_headings
        ]

        return [
            "attribute",
            *headings,
        ]
    @staticmethod
    def _get_primary_bbox(
        block: ContentBlock,
    ):

        if not block.provenance:
            return None

        return block.provenance[0].bbox