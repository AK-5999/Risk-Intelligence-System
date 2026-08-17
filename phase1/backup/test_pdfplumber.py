from pathlib import Path

import pdfplumber
import json

PDF_PATH = Path(r"D:\Coding\Vestas\Pipeline\data\VestasAnnualReport2025.pdf")
PAGE_NUMBER = 51


OUTPUT_JSON = Path("page_51_extraction.json")


def serialize(obj):
    """
    Convert non-serializable objects to string.
    """
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj

    if isinstance(obj, list):
        return [serialize(i) for i in obj]

    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}

    return str(obj)


def extract_page(pdf_path: Path, page_number: int):

    with pdfplumber.open(pdf_path) as pdf:

        page = pdf.pages[page_number - 1]

        data = {
            "page_number": page_number,
            "width": page.width,
            "height": page.height,

            "text": page.extract_text(),

            "words": page.extract_words(),

            "tables": page.extract_tables(),

            "characters": page.chars,

            "lines": page.lines,

            "rectangles": page.rects,

            "curves": page.curves,

            "images": page.images,
        }

        return serialize(data)


if __name__ == "__main__":

    result = extract_page(PDF_PATH, PAGE_NUMBER)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)

    print(f"Extraction saved to: {OUTPUT_JSON.resolve()}")