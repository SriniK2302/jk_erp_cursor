"""Rename direct child files using a date found in file contents."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
import re


_MONTHS_3 = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_FILE_TYPE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "all": (),
    "pdf": (".pdf",),
    "ppt": (".ppt", ".pptx"),
    "excel": (".xls", ".xlsx", ".xlsm", ".xlsb"),
    "word": (".doc", ".docx"),
}


@dataclass
class RenameByContentDateReport:
    root: Path
    scanned_count: int = 0
    renamed_count: int = 0
    skipped_paths: list[str] = field(default_factory=list)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_paths)


def _normalize_token(token: str) -> str:
    return token.strip().lower()


def _compile_date_pattern(pattern: str) -> re.Pattern[str]:
    s = (pattern or "").strip()
    if not s:
        raise ValueError("Date search pattern is required.")
    out: list[str] = []
    i = 0
    dd_seen = 0
    mm_seen = 0
    yy_seen = 0
    while i < len(s):
        ch = s[i]
        if ch.lower() in ("d", "m", "y"):
            j = i + 1
            while j < len(s) and s[j].lower() == ch.lower():
                j += 1
            tok = _normalize_token(s[i:j])
            if tok in ("d", "dd"):
                out.append(r"(?P<dd>\d{1,2})")
                dd_seen += 1
            elif tok in ("m", "mm"):
                out.append(r"(?P<mm>\d{1,2})")
                mm_seen += 1
            elif tok in ("mmm",):
                out.append(r"(?P<mmm>[A-Za-z]{3})")
                mm_seen += 1
            elif tok in ("yy",):
                out.append(r"(?P<yy>\d{2})")
                yy_seen += 1
            elif tok in ("yyyy",):
                out.append(r"(?P<yyyy>\d{4})")
                yy_seen += 1
            else:
                raise ValueError(
                    f"Unsupported token '{s[i:j]}'. Use dd, mm, mmm, yy, yyyy with separators."
                )
            i = j
            continue
        out.append(re.escape(ch))
        i += 1
    if dd_seen != 1 or mm_seen != 1 or yy_seen != 1:
        raise ValueError("Pattern must contain exactly one day, one month, and one year token.")
    return re.compile("".join(out), re.IGNORECASE)


def _coerce_match_to_date(match: re.Match[str]) -> date | None:
    gd = match.groupdict()
    try:
        dd = int(gd.get("dd") or "")
    except ValueError:
        return None

    mm: int | None = None
    if gd.get("mm"):
        try:
            mm = int(gd["mm"])
        except ValueError:
            return None
    elif gd.get("mmm"):
        mm = _MONTHS_3.get(gd["mmm"][:3].lower())
    if mm is None:
        return None

    year: int | None = None
    if gd.get("yyyy"):
        try:
            year = int(gd["yyyy"])
        except ValueError:
            return None
    elif gd.get("yy"):
        try:
            year = 2000 + int(gd["yy"])
        except ValueError:
            return None
    if year is None:
        return None

    try:
        return date(year, mm, dd)
    except ValueError:
        return None


def _read_text(path: Path) -> str | None:
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader  # lazy import (don't crash app startup)
        except ModuleNotFoundError:
            return None
        try:
            reader = PdfReader(str(path))
        except Exception:
            return None
        parts: list[str] = []
        for page in reader.pages:
            try:
                txt = page.extract_text() or ""
            except Exception:
                txt = ""
            if txt:
                parts.append(txt)
        joined = "\n".join(parts).strip()
        return joined or None

    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:4096]:
        return None
    for enc in ("utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def _prefix_for_date(dt: date) -> str:
    return f"{dt.year:04d} {dt.month:02d} {dt.day:02d}"


def _normalize_file_type(file_type: str) -> str:
    ft = (file_type or "all").strip().lower()
    if ft not in _FILE_TYPE_EXTENSIONS:
        raise ValueError("File type is invalid.")
    return ft


def _matches_file_type(path: Path, file_type: str) -> bool:
    exts = _FILE_TYPE_EXTENSIONS[file_type]
    if not exts:
        return True
    return path.suffix.lower() in exts


def rename_direct_files_by_content_date(
    root: Path, *, date_search_pattern: str, file_type: str = "all"
) -> RenameByContentDateReport:
    report = RenameByContentDateReport(root=root)
    rx = _compile_date_pattern(date_search_pattern)
    file_type_key = _normalize_file_type(file_type)
    if file_type_key == "pdf":
        try:
            import pypdf  # noqa: F401
        except ModuleNotFoundError as exc:
            raise ValueError(
                "PDF parsing requires the 'pypdf' package. Install it in the Python environment running the server."
            ) from exc
    for item in root.iterdir():
        if not item.is_file():
            continue
        if not _matches_file_type(item, file_type_key):
            continue
        report.scanned_count += 1
        text = _read_text(item)
        if text is None:
            report.skipped_paths.append(f"{item.name}: unreadable/binary file")
            continue
        dt: date | None = None
        for m in rx.finditer(text):
            dt = _coerce_match_to_date(m)
            if dt is not None:
                break
        if dt is None:
            report.skipped_paths.append(f"{item.name}: no valid date matched pattern")
            continue
        new_name = f"{_prefix_for_date(dt)} {item.name}"
        if new_name == item.name:
            continue
        target = item.with_name(new_name)
        if target.exists():
            report.skipped_paths.append(f"{item.name}: target already exists ({new_name})")
            continue
        try:
            item.rename(target)
        except OSError as exc:
            report.skipped_paths.append(f"{item.name}: {exc}")
            continue
        report.renamed_count += 1
    return report
