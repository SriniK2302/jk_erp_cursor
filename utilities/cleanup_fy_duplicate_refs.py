"""Clean up duplicate FYNN / 20NN references inside file names.

Only files whose name starts with a leading ``FYNN`` token (e.g. ``FY15``)
are processed. The leading token is kept as-is. Anywhere else in the name,
any further occurrence of that same ``FYNN`` or the equivalent full year
``20NN`` (case-insensitive) is stripped out, repeatedly, until none remain.
Everything else in the name is preserved, with a single space between the
remaining parts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_LEADING_FY_RE = re.compile(r"^FY(\d{2})", re.IGNORECASE)


@dataclass
class CleanupFYReport:
    root: Path
    scanned_count: int = 0
    renamed_count: int = 0
    skipped_paths: list[str] = field(default_factory=list)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_paths)


def _next_available_name(folder: Path, stem: str, suffix: str) -> str:
    base = f"{stem}{suffix}"
    if not (folder / base).exists():
        return base
    n = 2
    while True:
        candidate = f"{stem} v{n}{suffix}"
        if not (folder / candidate).exists():
            return candidate
        n += 1


def _collapse_spaces(text: str) -> str:
    return re.sub(r" {2,}", " ", text).strip()


def _strip_refs(rest: str, fy_token: str, year_token: str) -> str:
    """Repeatedly remove fy_token / year_token occurrences from rest."""
    fy_re = re.compile(re.escape(fy_token), re.IGNORECASE)
    year_re = re.compile(re.escape(year_token), re.IGNORECASE)

    changed = True
    while changed:
        changed = False
        new_rest = fy_re.sub(" ", rest)
        if new_rest != rest:
            rest = new_rest
            changed = True
        new_rest = year_re.sub(" ", rest)
        if new_rest != rest:
            rest = new_rest
            changed = True

    return rest


def cleanup_fy_duplicate_refs(root: Path) -> CleanupFYReport:
    report = CleanupFYReport(root=root)

    for item in root.iterdir():
        if not item.is_file():
            continue
        report.scanned_count += 1

        original_name = item.name
        stem = item.stem
        suffix = item.suffix

        match = _LEADING_FY_RE.match(stem)
        if not match:
            report.skipped_paths.append(f"{original_name}: does not start with FYNN")
            continue

        nn = match.group(1)
        fy_token = f"FY{nn}"
        year_token = f"20{nn}"

        leading = stem[: match.end()]
        rest = stem[match.end():]

        cleaned_rest = _strip_refs(rest, fy_token, year_token)
        new_stem = _collapse_spaces(f"{leading} {cleaned_rest}")

        if not new_stem:
            report.skipped_paths.append(f"{original_name}: resulting file name is empty")
            continue

        if new_stem == stem:
            report.skipped_paths.append(f"{original_name}: Compliant")
            continue

        final_name = _next_available_name(root, new_stem, suffix)
        if final_name == original_name:
            continue

        target = item.with_name(final_name)
        try:
            item.rename(target)
        except OSError as exc:
            report.skipped_paths.append(f"{original_name}: {exc}")
            continue
        report.renamed_count += 1

    return report
