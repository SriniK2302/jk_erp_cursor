"""Import Excel/CSV data into bank_transactions_source.

Specific to the BankTransactionSource table (not a generic import tool).
"""
from django.conf import settings

from utilities.excel_to_postgres import read_sheet_rows
from gl.bank_transactions.models import SourceBankCashAc


HEADER_TRANSLATORS = {
    "tran_date": ["tran date", "tran dt", "transaction date", "txn date", "date"],
    "value_date": ["value date", "value dt"],
    "narration": ["narration", "description", "particulars", "transaction remarks", "remarks"],
    "reference": ["chq", "cheque", "ref no", "reference", "chq / ref no", "chq/ref no", "utr", "chq no"],
    "debit": ["withdrawal", "withdrawals", "withdrawl", "debit", "debit amt"],
    "credit": ["deposit", "deposits", "credit", "credit amt"],
    "closing_balance": ["balance", "closing balance"],
    "source_ac": ["source ac", "source_ac", "account"],
}


def match_headers(headers: list[str]) -> dict:
    """Map raw file headers to canonical columns using HEADER_TRANSLATORS.
    Returns {canonical_name: matched_header_or_None}."""
    normalized = {h.strip().lower(): h for h in headers}
    result = {}
    for canonical, variants in HEADER_TRANSLATORS.items():
        found = None
        for variant in variants:
            if variant in normalized:
                found = normalized[variant]
                break
        result[canonical] = found
    return result


def check_required_columns(column_map: dict) -> list[str]:
    """Return list of missing canonical column names, or [] if all found."""
    required = ["tran_date", "narration", "debit", "credit", "value_date", "reference", "closing_balance", "source_ac"]
    return [col for col in required if not column_map.get(col)]


def validate_source_ac(source_ac: str) -> bool:
    """Check source_ac exists in the Source Accounts master table."""
    return SourceBankCashAc.objects.filter(source_ac=source_ac).exists()


def build_dataset(rows: list[dict], column_map: dict) -> list[dict]:
    """Build the final row dataset: parsed dates, value_date fallback,
    source_ac attached to every row."""
    dataset = []
    for row in rows:
        tran_date = row.get(column_map["tran_date"])
        if tran_date and "T" in tran_date:
            tran_date = tran_date.split("T")[0]
        value_date = row.get(column_map["value_date"]) or tran_date
        if value_date and "T" in value_date:
            value_date = value_date.split("T")[0]
        dataset.append({
            "tran_date": tran_date,
            "value_date": value_date,
            "narration": row.get(column_map["narration"]),
            "debit": row.get(column_map["debit"]),
            "credit": row.get(column_map["credit"]),
            "reference": row.get(column_map["reference"]),
            "closing_balance": row.get(column_map["closing_balance"]),
            "source_ac": row.get(column_map["source_ac"]),
        })
    return dataset


def preview_dataset(dataset: list[dict]) -> dict:
    """Return preview-ready structure: full row list + match count summary."""
    return {"rows": dataset, "total_count": len(dataset), "match_count": len(dataset)}


def commit_dataset_to_postgres(dataset: list[dict], postgres_db: str, table_name: str) -> dict:
    """Insert the orchestrator dataset rows into the selected table.
    Returns {"ok": bool, "inserted": int, "message": str}."""
    pass


def orchestrate_import_preview(file_path, sheet_name, context: dict) -> dict:
    """
    Runs: match_headers -> check_required_columns (abort if missing)
    -> validate_source_ac per row (abort if invalid)
    -> build_dataset -> preview_dataset.
    Returns preview + match count for user decision (proceed/abandon).
    Does NOT write to postgres.
    """
    headers, rows = read_sheet_rows(file_path, sheet_name)
    column_map = match_headers(headers)
    missing = check_required_columns(column_map)
    if missing:
        return {"ok": False, "stage": "check_required_columns", "message": f"Missing columns: {', '.join(missing)}"}

    source_ac_col = column_map["source_ac"]
    source_ac_idx = headers.index(source_ac_col)
    for row_num, row in enumerate(rows, start=2):
        source_ac_value = row[source_ac_idx]
        if not validate_source_ac(source_ac_value):
            return {"ok": False, "stage": "validate_source_ac", "message": f"Row {row_num}: invalid source_ac '{source_ac_value}'"}

    row_dicts = [dict(zip(headers, row)) for row in rows]
    dataset = build_dataset(row_dicts, column_map)
    preview = preview_dataset(dataset)
    return {"ok": True, "stage": "preview_dataset", "message": "Preview ready.", "column_map": column_map, **preview}
