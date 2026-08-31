"""Prefix ITR tax files (.xml or .json) with FYnn based on the AssessmentYear
value found inside each file.

FY is derived as the last two digits of the AssessmentYear value itself
(e.g. AssessmentYear 2007 -> FY07, AssessmentYear 2021 -> FY21).

Only direct .xml and .json files in the given folder are scanned (no
subfolders).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

_ASSESSMENT_YEAR_KEY = "assessmentyear"


@dataclass
class PrefixFYFromTaxFilesReport:
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


def _find_assessment_year_in_xml(xml_path: Path) -> str | None:
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return None
    root = tree.getroot()
    for elem in root.iter():
        tag = elem.tag
        local = tag.split("}", 1)[1] if "}" in tag else tag
        if local.lower() == _ASSESSMENT_YEAR_KEY:
            text = (elem.text or "").strip()
            if text:
                return text
    return None


def _find_assessment_year_in_json(value) -> str | None:
    if isinstance(value, dict):
        for key, val in value.items():
            if key.lower() == _ASSESSMENT_YEAR_KEY:
                if val is not None and str(val).strip():
                    return str(val).strip()
            found = _find_assessment_year_in_json(val)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_assessment_year_in_json(item)
            if found:
                return found
    return None


def _find_assessment_year(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".xml":
        return _find_assessment_year_in_xml(path)
    if suffix == ".json":
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None
        return _find_assessment_year_in_json(data)
    return None


def prefix_fy_from_tax_files(root: Path) -> PrefixFYFromTaxFilesReport:
    report = PrefixFYFromTaxFilesReport(root=root)

    for item in root.iterdir():
        if not item.is_file() or item.suffix.lower() not in (".xml", ".json"):
            continue
        report.scanned_count += 1

        original_name = item.name
        stem = item.stem
        suffix = item.suffix

        assessment_year = _find_assessment_year(item)
        if not assessment_year:
            report.skipped_paths.append(f"{original_name}: AssessmentYear not found")
            continue

        match = re.search(r"(\d{4})", assessment_year)
        if not match:
            report.skipped_paths.append(
                f"{original_name}: AssessmentYear value not a 4-digit year ({assessment_year})"
            )
            continue

        year = match.group(1)
        fy_token = f"FY{year[-2:]}"

        if stem == fy_token or stem.startswith(fy_token + " "):
            report.skipped_paths.append(f"{original_name}: Compliant")
            continue

        new_stem = f"{fy_token} {stem}"
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
