"""Rename direct child files using configurable date patterns."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class RenameDatePrefixReport:
    root: Path
    scanned_count: int = 0
    renamed_count: int = 0
    skipped_paths: list[str] = field(default_factory=list)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_paths)


def _split_pattern(pattern: str) -> list[tuple[str, str]]:
    """Split pattern into [("field","yy"), ("lit","-"), ...]."""
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch.lower() in ("y", "m", "d"):
            j = i + 1
            while j < len(pattern) and pattern[j].lower() == ch.lower():
                j += 1
            out.append(("field", pattern[i:j]))
            i = j
            continue
        j = i + 1
        while j < len(pattern) and pattern[j].lower() not in ("y", "m", "d"):
            j += 1
        out.append(("lit", pattern[i:j]))
        i = j
    return out


def _pattern_has_date_field(parts: list[tuple[str, str]], letter: str) -> bool:
    letter = letter.lower()
    return any(
        kind == "field" and token[0].lower() == letter
        for kind, token in parts
    )


def _parse_leading_date_from_pattern(name: str, pattern: str) -> tuple[date, int] | None:
    """Parse a date from start of name using the supplied pattern."""
    parts = _split_pattern(pattern)
    pos = 0
    yy: int | None = None
    yyyy: int | None = None
    mm: int | None = None
    dd: int | None = None

    for kind, token in parts:
        if kind == "lit":
            if not name.startswith(token, pos):
                return None
            pos += len(token)
            continue
        ln = len(token)
        chunk = name[pos : pos + ln]
        if len(chunk) != ln or not chunk.isdigit():
            return None
        t = token[0].lower()
        val = int(chunk)
        if t == "y":
            if ln == 2:
                yy = val
            elif ln == 4:
                yyyy = val
            else:
                return None
        elif t == "m":
            if ln != 2:
                return None
            if not (1 <= val <= 12):
                return None
            mm = val
        elif t == "d":
            if ln != 2:
                return None
            dd = val
        pos += ln

    if dd is None and not _pattern_has_date_field(parts, "d"):
        dd = 1

    year = yyyy if yyyy is not None else (2000 + yy if yy is not None else None)
    if year is None or mm is None or dd is None:
        return None
    try:
        dt = date(year, mm, dd)
    except ValueError:
        return None
    return (dt, pos)


def _parse_date_from_pattern(
    name: str, pattern: str, *, start_only: bool
) -> tuple[date, int, int] | None:
    """
    Parse ``pattern`` against ``name``.

    If ``start_only`` is True, only the beginning of ``name`` is considered
    (same as :func:`_parse_leading_date_from_pattern`). Otherwise the first
    offset ``j`` where the pattern matches ``name[j:]`` is used.

    Returns ``(date, consumed_length, start_offset)`` or ``None``.
    """
    if start_only:
        hit = _parse_leading_date_from_pattern(name, pattern)
        if hit is None:
            return None
        dt, consumed = hit
        return (dt, consumed, 0)
    for j in range(0, len(name)):
        hit = _parse_leading_date_from_pattern(name[j:], pattern)
        if hit is not None:
            dt, consumed = hit
            return (dt, consumed, j)
    return None


def _render_date_with_pattern(dt: date, pattern: str) -> str:
    """Render date using Y/M/D tokens in replacement pattern."""
    out: list[str] = []
    for kind, token in _split_pattern(pattern):
        if kind == "lit":
            out.append(token)
            continue
        ln = len(token)
        t = token[0].lower()
        if t == "y":
            if ln == 2:
                out.append(f"{dt.year % 100:02d}")
            elif ln == 4:
                out.append(f"{dt.year:04d}")
            else:
                raise ValueError("Year token must be YY or YYYY.")
        elif t == "m":
            if ln != 2:
                raise ValueError("Month token must be MM.")
            out.append(f"{dt.month:02d}")
        elif t == "d":
            if ln != 2:
                raise ValueError("Day token must be DD.")
            out.append(f"{dt.day:02d}")
    return "".join(out)


def _ensure_space_between(left: str, right: str) -> str:
    """
    Concatenate ``left`` and ``right``. If both are non-empty, the last
    character of ``left`` is not whitespace, and the first character of
    ``right`` is not whitespace, insert a single ASCII space between them.
    """
    if not left:
        return right
    if not right:
        return left
    if (not left[-1].isspace()) and (not right[0].isspace()):
        return f"{left} {right}"
    return f"{left}{right}"


def rename_direct_files_date_prefix(
    root: Path,
    *,
    trim_left_until: str = "",
    existing_pattern: str = "YYMMDD",
    replacement_pattern: str = "YYYY MM DD",
    pattern_start_only: bool = True,
) -> RenameDatePrefixReport:
    """
    Rename only files directly under root.

    ``pattern_start_only``: if True, the first match must be at the start
    (after optional marker trim); the matched characters are **replaced** by
    the rendered replacement. If False, the first match anywhere is used only
    to derive the date for the replacement text; that replacement is then
    **prepended at the left** of the **full** original file name (entire name
    unchanged after the new prefix).

    When the replacement meets another non-whitespace character (before or
    after it in the final name), a single ASCII space is inserted at that
    boundary.
    """
    report = RenameDatePrefixReport(root=root)
    marker = (trim_left_until or "").strip()
    src_pattern = (existing_pattern or "").strip()
    dst_raw = replacement_pattern or ""
    if not dst_raw.strip():
        raise ValueError("Replacement pattern is required.")
    dst_pattern = dst_raw
    for item in root.iterdir():
        if not item.is_file():
            continue
        report.scanned_count += 1
        original_name = item.name
        working_name = original_name
        idx = 0
        if marker:
            mpos = original_name.find(marker)
            if mpos < 0:
                report.skipped_paths.append(
                    f"{original_name}: marker '{marker}' not found"
                )
                continue
            working_name = original_name[mpos:]
            idx = mpos
        else:
            working_name = original_name

        parsed = _parse_date_from_pattern(
            working_name, src_pattern, start_only=pattern_start_only
        )
        if parsed is None:
            report.skipped_paths.append(
                f"{original_name}: no valid date for pattern '{src_pattern}'"
            )
            continue
        dt, consumed, rel_off = parsed
        label = _render_date_with_pattern(dt, dst_pattern)
        if pattern_start_only:
            abs_start = idx + rel_off
            prefix = original_name[:abs_start]
            rest = original_name[abs_start + consumed :]
            new_name = _ensure_space_between(
                prefix, _ensure_space_between(label, rest)
            )
        else:
            new_name = _ensure_space_between(label, original_name)
        if new_name == original_name:
            continue
        target = item.with_name(new_name)
        if target.exists():
            report.skipped_paths.append(f"{original_name}: target already exists ({new_name})")
            continue
        try:
            item.rename(target)
        except OSError as exc:
            report.skipped_paths.append(f"{original_name}: {exc}")
            continue
        report.renamed_count += 1
    return report
