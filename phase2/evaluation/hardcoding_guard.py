from __future__ import annotations

import json
import re
from pathlib import Path


def normalize_text(
    value: str,
) -> str:

    value = (
        str(value)
        .lower()
        .strip()
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value


def load_golden_titles(
    golden_path: Path,
) -> list[str]:
    """
    Load all Vestas-specific expected risk titles directly from
    the golden set.

    The guard therefore stays synchronized automatically whenever
    the golden set changes.
    """

    if not golden_path.exists():

        raise FileNotFoundError(
            f"Golden set not found: "
            f"{golden_path}"
        )

    with golden_path.open(
        "r",
        encoding="utf-8",
    ) as file:

        golden = json.load(
            file
        )

    titles = []

    for risk in golden.get(
        "risks",
        [],
    ):

        title = risk.get(
            "title"
        )

        if title:

            titles.append(
                normalize_text(
                    title
                )
            )

    return titles


def main() -> None:

    base_dir = (
        Path(__file__)
        .resolve()
        .parent
        .parent
    )

    golden_path = (
        base_dir
        / "evaluation"
        / "golden_set.json"
    )

    forbidden_titles = (
        load_golden_titles(
            golden_path
        )
    )

    # --------------------------------------------------------------
    # Production source files that influence extraction/generation.
    #
    # Do NOT scan evaluation/, prompts/, or test fixtures because
    # those are expected to contain golden-set terminology.
    # --------------------------------------------------------------

    files_to_check = [
        (
            base_dir
            / "src"
            / "risk_analyzer.py"
        ),
        (
            base_dir
            / "src"
            / "risk_candidate_extractor.py"
        ),
        (
            base_dir
            / "src"
            / "category_resolver.py"
        ),
        (
            base_dir
            / "src"
            / "risk_generator.py"
        ),
        (
            base_dir
            / "src"
            / "validator.py"
        ),
    ]

    violations = []

    for path in files_to_check:

        if not path.exists():

            print(
                f"WARNING: source file not found: "
                f"{path}"
            )

            continue

        content = (
            path.read_text(
                encoding="utf-8"
            )
            .lower()
        )

        content = re.sub(
            r"\s+",
            " ",
            content,
        )

        for title in forbidden_titles:

            if title in content:

                violations.append(
                    {
                        "file": (
                            str(path)
                        ),
                        "golden_title": (
                            title
                        ),
                    }
                )

    if violations:

        print(
            "\nHardcoding guard FAILED"
        )

        print(
            "------------------------"
        )

        for violation in violations:

            print(
                f"File : "
                f"{violation['file']}"
            )

            print(
                f"Title: "
                f"{violation['golden_title']}"
            )

            print()

        raise SystemExit(
            1
        )

    print(
        "\nHardcoding guard PASSED"
    )

    print(
        "------------------------"
    )

    print(
        f"Golden titles checked: "
        f"{len(forbidden_titles)}"
    )

    print(
        f"Source files checked: "
        f"{len(files_to_check)}"
    )


if __name__ == "__main__":
    main()