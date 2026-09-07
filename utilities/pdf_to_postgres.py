"""
Import bank transaction rows from a PDF statement into PostgreSQL.

Separate module for PDF-format bank statements. Built incrementally;
will be wired into the import pipeline later.
"""

from __future__ import annotations

import re
from collections import defaultdict

import pdfplumber

_HEADER_KEYWORDS = (
    "tran date", "tran dt", "tran id", "value date", "value dt",
    "deposit", "deposits", "withdrawal", "withdrawals", "withdrawl",
    "narration", "reference", "remarks", "chq", "cheque", "balance",
)

_SINGLE_LINE_PASS_SCORE = 6
_TWO_LINE_PASS_SCORE = 5

_AMOUNT_OR_NA_RE = re.compile(r'(?:NA|-?[\d][\d,]*\.\d{2})')
_STOP_MARKERS = ('statement summary', 'end of statement', 'generation date')

_DATE_FORMATS = (
    {
        "name": "ddmmyyyy",
        "date_regex": re.compile(r'\b\d{2}/\d{2}/\d{4}\b'),
        "row_start_regex": re.compile(r'^\d{2}/\d{2}/\d{4}\b'),
        "amount_position": "trailing",
    },
    {
        "name": "ddmonyyyy",
        "date_regex": re.compile(r'\d{2}-[A-Za-z]{3}-\s?\d{4}'),
        "row_start_regex": re.compile(r'^\d+\s+\S+\s'),
        "amount_position": "after_dates",
    },
)


def _score_line(line: str) -> int:
    lower = line.lower()
    return sum(1 for kw in _HEADER_KEYWORDS if kw in lower)


def _group_words_by_gap(row_words: list[dict], gap_thresh: float = 10.0) -> list[str]:
    """Merge words on the same line into columns using x-position gaps
    (small gap = same column, e.g. 'Ref' + 'No.' -> 'Ref No.')."""
    row_words = sorted(row_words, key=lambda w: w["x0"])
    columns = []
    cur = ""
    prev_x1 = None
    for w in row_words:
        if prev_x1 is not None and (w["x0"] - prev_x1) > gap_thresh:
            if cur:
                columns.append(cur)
            cur = ""
        cur = f"{cur} {w['text']}".strip()
        prev_x1 = w["x1"]
    if cur:
        columns.append(cur)
    return columns


def _reconstruct_words(line_chars: list[dict], gap_thresh: float = 2.0) -> list[str]:
    """Group same-line chars into words using x-position gaps (for PDFs
    where extract_text() garbles overlapping/fragmented text)."""
    line_chars = sorted(line_chars, key=lambda c: c["x0"])
    words = []
    cur = ""
    prev_x1 = None
    for c in line_chars:
        if prev_x1 is not None and (c["x0"] - prev_x1) > gap_thresh:
            if cur:
                words.append(cur)
            cur = ""
        cur += c["text"]
        prev_x1 = c["x1"]
    if cur:
        words.append(cur)
    return words


def find_header_single_line(page) -> list[str] | None:
    """
    Technique 1: one text line scores >= _SINGLE_LINE_PASS_SCORE keyword
    matches. Returns its columns (grouped by word x-position gaps), or
    None if no single line passes.
    """
    lines = (page.extract_text() or "").splitlines()
    best_line = max(lines, key=_score_line, default=None)
    if not best_line or _score_line(best_line) < _SINGLE_LINE_PASS_SCORE:
        return None

    words = page.extract_words()
    by_top = defaultdict(list)
    for w in words:
        by_top[round(w["top"])].append(w)

    for row in by_top.values():
        row_text = " ".join(w["text"] for w in sorted(row, key=lambda w: w["x0"]))
        if row_text == best_line:
            return _group_words_by_gap(row)
    return best_line.split()


def find_header_two_line(page) -> list[str] | None:
    """
    Technique 2: header wrapped across two adjacent lines (e.g. "Tran" /
    "ID" -> "Tran ID"). Pairs each word on the second line to the nearest
    word (by x-position) on the first line. Returns None if no adjacent
    pair scores >= _TWO_LINE_PASS_SCORE.
    """
    words = page.extract_words()
    by_top = defaultdict(list)
    for w in words:
        by_top[round(w["top"])].append(w)

    tops = sorted(by_top)
    for i in range(len(tops) - 1):
        row_a = sorted(by_top[tops[i]], key=lambda w: w["x0"])
        row_b = sorted(by_top[tops[i + 1]], key=lambda w: w["x0"])
        combined_text = " ".join(w["text"] for w in row_a + row_b)
        if _score_line(combined_text) < _TWO_LINE_PASS_SCORE:
            continue

        columns: dict[int, list[str]] = {j: [w["text"]] for j, w in enumerate(row_a)}
        for w in row_b:
            nearest_idx = min(
                range(len(row_a)),
                key=lambda j: abs(row_a[j]["x0"] - w["x0"]),
            )
            columns[nearest_idx].append(w["text"])
        return [" ".join(columns[j]) for j in sorted(columns)]
    return None


def find_header_row(pdf_path) -> list[str] | None:
    """
    Identify the header row on the first page and return its column names.
    Tries find_header_single_line, then find_header_two_line, then
    char-gap reconstruction (for fragmented/overlapping text extraction).
    Returns None if no technique finds a header.
    """
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return None
        page = pdf.pages[0]

        result = find_header_single_line(page)
        if result is not None:
            return result

        result = find_header_two_line(page)
        if result is not None:
            return result

        chars = page.chars
        by_top_chars = defaultdict(list)
        for c in chars:
            by_top_chars[round(c["top"], 1)].append(c)

        for t in sorted(by_top_chars):
            words = _reconstruct_words(by_top_chars[t])
            joined = " ".join(words)
            if _score_line(joined) >= 3:
                return words

    return None


def detect_date_format(pdf_path) -> str | None:
    """Scan the first page and return the name of the first date format
    in _DATE_FORMATS that matches, or None if none match."""
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return None
        lines = (pdf.pages[0].extract_text() or "").splitlines()
    for fmt in _DATE_FORMATS:
        match_count = sum(1 for l in lines if fmt["row_start_regex"].match(l.strip()))
        if match_count >= 2:
            return fmt["name"]
    return None


def _extract_transactions_generic(pdf_path, fmt: dict) -> list[dict]:
    """
    Extract transaction rows using the given format's regex config
    (from _DATE_FORMATS). Handles both amount_position styles:
    "trailing" (last 3 amounts in the block) and "after_dates" (first 3
    amounts after the second date).
    """
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            raw_lines = (page.extract_text() or "").splitlines()
            lines = []
            for l in raw_lines:
                if any(l.strip().lower().startswith(m) for m in _STOP_MARKERS):
                    break
                lines.append(l)

            row_start_idxs = [i for i, l in enumerate(lines) if fmt["row_start_regex"].match(l.strip())]
            for pos, idx in enumerate(row_start_idxs):
                next_idx = row_start_idxs[pos + 1] if pos + 1 < len(row_start_idxs) else len(lines)
                block = " ".join(lines[idx:next_idx])
                block = re.sub(r'(\d{2}-[A-Za-z]{3}-)\s+(\d{4})', r'\1\2', block)

                date_matches = list(fmt["date_regex"].finditer(block))
                if len(date_matches) < 2:
                    continue

                if fmt["amount_position"] == "trailing":
                    amount_matches = list(_AMOUNT_OR_NA_RE.finditer(block))
                    if len(amount_matches) < 3:
                        continue
                    a, b, c = (m.group() for m in amount_matches[-3:])
                else:
                    after_dates = block[date_matches[1].end():]
                    amount_matches = list(_AMOUNT_OR_NA_RE.finditer(after_dates))
                    if len(amount_matches) < 3:
                        continue
                    a, b, c = (m.group() for m in amount_matches[:3])

                def _num(x):
                    return None if x == "NA" else float(x.replace(",", ""))

                rows.append({
                    "tran_date": date_matches[0].group(),
                    "value_date": date_matches[1].group(),
                    "credit": _num(a),
                    "debit": _num(b),
                    "closing_balance": _num(c),
                })
    return rows


def extract_transactions(pdf_path) -> list[dict]:
    """Detect the date format, then convert using the generic extractor."""
    name = detect_date_format(pdf_path)
    fmt = next((f for f in _DATE_FORMATS if f["name"] == name), None)
    if fmt is None:
        return []
    return _extract_transactions_generic(pdf_path, fmt)
