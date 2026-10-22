"""Offline prep for tasks_kodoc.py: PDF -> per-page text with PyMuPDF (not needed on the company PC).

    uv run --no-project --with pymupdf python bench/kodoc_extract.py

Reads bench/ext/kodoc/documents.csv and bench/ext/kodoc/pdf/{row:02d}.pdf (row = 0-based row of documents.csv),
writes bench/ext/kodoc/text/{row:02d}.json = {"file_name", "pages_expected", "pages": [text of page 1, ...]}.
Text is page.get_text("text") with NFC normalisation (some PDFs store Hangul as decomposed jamo).
"""
import csv
import json
import sys
import unicodedata
from pathlib import Path

import pymupdf

EXT = Path(__file__).resolve().parent / "ext" / "kodoc"


def main():
    rows = list(csv.DictReader((EXT / "documents.csv").open(encoding="utf-8")))
    (EXT / "text").mkdir(exist_ok=True)
    for i, r in enumerate(rows):
        pdf = EXT / "pdf" / f"{i:02d}.pdf"
        if not pdf.exists() or pdf.read_bytes()[:4] != b"%PDF":
            print(i, "no pdf")
            continue
        try:
            doc = pymupdf.open(pdf)
            pages = [unicodedata.normalize("NFC", p.get_text("text")) for p in doc]
        except Exception as e:                      # broken file
            print(i, "error", e)
            continue
        (EXT / "text" / f"{i:02d}.json").write_text(json.dumps(
            {"file_name": r["file_name"], "pages_expected": int(r["pages"]), "pages": pages},
            ensure_ascii=False), encoding="utf-8")
        print(i, len(pages), "pages, expected", r["pages"], "" if len(pages) == int(r["pages"]) else "MISMATCH")


if __name__ == "__main__":
    sys.exit(main())
