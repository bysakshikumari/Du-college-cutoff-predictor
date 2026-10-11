"""Rebuild data/du_cutoffs.csv from the DU "minimum allocation score" PDFs.

    pip install pdfplumber pandas
    python scripts/build_data.py path/to/pdf_folder

The parser is tuned to the 2025/2026 PDF layouts; a new layout may need small tweaks.
Output columns: year, round, college, course, category, cutoff_score
"""
import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

OUT = Path(__file__).resolve().parents[1] / "data" / "du_cutoffs.csv"
NUMBER = re.compile(r"^\d+(\.\d+)?$")
CATEGORY_WORDS = {"UR", "SC", "ST", "EWS", "SIKH", "PwBD", "KM", "SGC"}


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def parse_2026(path, rnd):
    """Wide tables with blank cells: give each number to the nearest category header."""
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            header = {}  # category -> x position of its header
            for w in words:
                name = {"NCL": "OBC", "FEMALE": "OF", "MALE": "OM"}.get(w["text"], w["text"] if w["text"] in CATEGORY_WORDS else None)
                if name and w["top"] < 260:
                    header[name] = (w["x0"] + w["x1"]) / 2
            if "UR" not in header:
                continue
            table = page.find_tables()[0]
            xs = sorted({round(c[0]) for c in table.cells})
            college_x, course_x = xs[1], xs[2]
            for r in table.rows:
                cells = [c for c in r.cells if c]
                top, bottom = min(c[1] for c in cells), max(c[3] for c in cells)
                line = sorted((w for w in words if w["top"] >= top - 1 and w["bottom"] <= bottom + 1), key=lambda w: (round(w["top"] / 3), w["x0"]))
                if not any(w["x1"] < 70 and w["text"].isdigit() for w in line):
                    continue  # not a data row
                college = clean(" ".join(w["text"] for w in line if college_x - 2 <= w["x0"] < course_x - 2))
                course = clean(" ".join(w["text"] for w in line if course_x - 2 <= w["x0"] < header["UR"] - 20))
                for w in line:
                    if NUMBER.match(w["text"]) and w["x0"] >= header["UR"] - 25:
                        middle = (w["x0"] + w["x1"]) / 2
                        rows.append((2026, rnd, college, course, min(header, key=lambda k: abs(header[k] - middle)), float(w["text"])))
    return rows


def table_rows(path):
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for r in table:
                    if r and str(r[0] or "").strip().isdigit():
                        yield r


def parse_2025_r1(path):
    columns = {"UR": 9, "OBC": 12, "SC": 15, "ST": 18, "EWS": 21, "PwBD": 24}
    return [(2025, "R1", clean(r[3]), clean(r[6]), cat, float(r[i]))
            for r in table_rows(path) for cat, i in columns.items() if r[i] and NUMBER.match(r[i].strip())]


def parse_2025_spot(path):
    return [(2025, "Spot", clean(r[2]), clean(r[1]), r[3].strip(), float(r[4])) for r in table_rows(path) if r[4] and NUMBER.match(r[4].strip())]


def match_key(name):
    """Ignores punctuation and wording differences so 2025 and 2026 names line up."""
    name = name.lower().replace(".", "").replace("programme", "program")
    return re.sub(r"\s+", " ", name).replace(" / ", "/").strip()


def tidy_2025(course):
    course = re.sub(r"^B\.(Sc|Com)\s*(\(|$)", lambda m: f"B.{m.group(1)}.{' (' if m.group(2) else ''}", course)
    return course.replace("B.A Program", "B.A. Program")


def main(folder):
    f = Path(folder)
    rows = (parse_2026(f / "2026_Round_One_CutOff_DU.pdf", "R1") + parse_2026(f / "2026_Round_Two_Cutoff_DU.pdf", "R2")
            + parse_2026(f / "2026_SpotRound_Cutoff_DU.pdf", "Spot") + parse_2025_r1(f / "2025_Round_One_CutOff_DU.pdf")
            + parse_2025_spot(f / "2025_SpotRound_CutOff_DU.pdf"))
    df = pd.DataFrame(rows, columns=["year", "round", "college", "course", "category", "cutoff_score"])
    df["course"] = [c if y == 2026 else tidy_2025(c) for y, c in zip(df["year"], df["course"])]
    # one spelling per college/course: the first one seen, 2026 wording first
    df = df.sort_values("year", ascending=False, kind="stable")
    for col in ["college", "course"]:
        df[col] = df.groupby(df[col].map(match_key))[col].transform("first")
    df = df.groupby(["year", "round", "college", "course", "category"], as_index=False)["cutoff_score"].first()
    df.sort_values(["college", "course", "year", "round", "category"]).to_csv(OUT, index=False)
    print(f"{len(df):,} rows -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
