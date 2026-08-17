from __future__ import annotations

import re


class TextNormalizer:
    """
    Conservative text cleanup for parsed PDF content.

    This component removes extraction artifacts while
    preserving the original semantic content.
    """

    CONTROL_CHARACTER_PATTERN = re.compile(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f]"
    )

    MULTIPLE_SPACES_PATTERN = re.compile(
        r"[ \t]+"
    )

    MULTIPLE_NEWLINES_PATTERN = re.compile(
        r"\n{3,}"
    )

    def normalize(
        self,
        text: str | None,
    ) -> str:

        if not text:
            return ""

        text = text.replace(
            "\u0007",
            " "
        )

        text = text.replace(
            "\xa0",
            " "
        )

        text = self.CONTROL_CHARACTER_PATTERN.sub(
            " ",
            text
        )

        lines: list[str] = []

        for line in text.splitlines():

            line = (
                self.MULTIPLE_SPACES_PATTERN
                .sub(
                    " ",
                    line
                )
                .strip()
            )

            if line:
                lines.append(line)

        text = "\n".join(lines)

        text = (
            self.MULTIPLE_NEWLINES_PATTERN
            .sub(
                "\n\n",
                text
            )
        )

        return text.strip()