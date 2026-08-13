"""Connect to PostgreSQL with caller-supplied credentials; list tables/columns; delete rows safely."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql

ALLOWED_SQL_OPERATORS = frozenset(
    ("=", "<>", "!=", "<", ">", "<=", ">=", "LIKE", "ILIKE")
)


def _validate_host(host: str) -> bool:
    h = (host or "").strip()
    if not h or len(h) > 253:
        return False
    if re.search(r"[\s'\x00-\x1f]", h):
        return False
    return True


def _validate_port(port: int) -> bool:
    return 1 <= port <= 65535


def _validate_db_or_user(s: str) -> bool:
    t = (s or "").strip()
    if not t or len(t) > 63:
        return False
    if re.search(r"[\s'\x00-\x1f]", t):
        return False
    return True


def _validate_table_name(name: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,62}", name))


def connect_with_params(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    dbname: str,
    connect_timeout: int = 10,
) -> psycopg.Connection:
    if not _validate_host(host):
        raise ValueError("Invalid host (empty, too long, or disallowed characters).")
    if not _validate_port(port):
        raise ValueError("Invalid port (use 1–65535).")
    if not _validate_db_or_user(user):
        raise ValueError("Invalid username.")
    if not _validate_db_or_user(dbname):
        raise ValueError("Invalid database name.")
    return psycopg.connect(
        host=host.strip(),
        port=port,
        user=user.strip(),
        password=password or "",
        dbname=dbname.strip(),
        connect_timeout=connect_timeout,
    )


def list_database_names(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    dbname: str,
) -> list[str]:
    """
    List databases the role can connect to (non-template, connections allowed).
    Connect using ``dbname`` (often ``postgres``) then query ``pg_database``.
    """
    with connect_with_params(
        host=host, port=port, user=user, password=password, dbname=dbname
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT datname
                FROM pg_catalog.pg_database
                WHERE datallowconn
                  AND NOT datistemplate
                ORDER BY datname
                """
            )
            return [r[0] for r in cur.fetchall()]


def test_pg_connection(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    dbname: str,
) -> dict[str, Any]:
    """Open a connection and run a trivial query; raises on failure."""
    with connect_with_params(
        host=host, port=port, user=user, password=password, dbname=dbname
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.execute("SELECT current_database(), current_user")
            db, role = cur.fetchone()
    return {"database": db, "user": role}


def list_public_tables(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    dbname: str,
) -> list[str]:
    with connect_with_params(
        host=host, port=port, user=user, password=password, dbname=dbname
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tablename
                FROM pg_catalog.pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
                """
            )
            return [r[0] for r in cur.fetchall()]


def list_table_columns(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    dbname: str,
    table_name: str,
) -> list[str]:
    if not (table_name or "").strip():
        raise ValueError("Table name required.")
    with connect_with_params(
        host=host, port=port, user=user, password=password, dbname=dbname
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_catalog = current_database()
                  AND table_schema = 'public'
                  AND lower(table_name) = lower(%s)
                ORDER BY ordinal_position
                """,
                (table_name,),
            )
            cols = [r[0] for r in cur.fetchall()]
            if not cols:
                raise ValueError("Table not found in schema public, or it has no columns.")
            return cols


def delete_rows_public(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    dbname: str,
    table_name: str,
    delete_all: bool,
    delete_all_confirm: str,
    filters: list[tuple[str, str, str]],
) -> dict[str, Any]:
    """
    Delete rows in ``public.table_name``.

    Either ``delete_all`` is True and ``delete_all_confirm`` must match
    ``table_name`` exactly, or at least one filter (column, operator, value)
    with a column that exists on the table and an allowed operator.
    """
    if not (table_name or "").strip():
        raise ValueError("Table name required.")

    with connect_with_params(
        host=host, port=port, user=user, password=password, dbname=dbname
    ) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tablename
                FROM pg_catalog.pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
                """
            )
            tables = [r[0] for r in cur.fetchall()]
            by_lower = {t.lower(): t for t in tables}
            resolved = by_lower.get(table_name.lower())
            if not resolved:
                raise ValueError(
                    "Table is not in the public schema list for this database."
                )

            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_catalog = current_database()
                  AND table_schema = 'public'
                  AND lower(table_name) = lower(%s)
                ORDER BY ordinal_position
                """,
                (resolved,),
            )
            col_rows = cur.fetchall()
            if not col_rows:
                raise ValueError(
                    "Table not found in schema public, or it has no columns."
                )
            col_lower = {r[0].lower(): r[0] for r in col_rows}

            if delete_all:
                confirm = (delete_all_confirm or "").strip()
                if confirm != resolved:
                    raise ValueError(
                        "To delete all rows, type the exact table name in the confirmation field."
                    )
                stmt = sql.SQL("DELETE FROM {}").format(sql.Identifier(resolved))
                cur.execute(stmt)
            else:
                where_parts: list[sql.SQL] = []
                params: list[Any] = []
                for col, op, val in filters:
                    col = (col or "").strip()
                    op = (op or "").strip().upper()
                    val = val if val is not None else ""
                    if not col or not op:
                        continue
                    if op not in ALLOWED_SQL_OPERATORS:
                        raise ValueError(f"Operator not allowed: {op!r}")
                    canon = col_lower.get(col.lower())
                    if not canon:
                        raise ValueError(f"Unknown column for this table: {col!r}")
                    where_parts.append(
                        sql.SQL("{} {} {}").format(
                            sql.Identifier(canon),
                            sql.SQL(op),
                            sql.Placeholder(),
                        )
                    )
                    params.append(val)
                if not where_parts:
                    raise ValueError(
                        "Add at least one column filter, or use delete-all-rows with confirmation."
                    )
                stmt = sql.SQL("DELETE FROM {} WHERE {}").format(
                    sql.Identifier(resolved),
                    sql.SQL(" AND ").join(where_parts),
                )
                cur.execute(stmt, params)
            deleted = cur.rowcount
        conn.commit()

    return {"deleted": deleted, "table": resolved, "database": dbname.strip()}


_MAX_ANALYSIS_LABEL_COLS = 12
_MAX_ANALYSIS_VALUE_COLS = 16
_MAX_SUMMARY_ROWS = 5000


def summarize_public_table_group_by(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    dbname: str,
    table_name: str,
    label_columns: list[str],
    value_columns: list[str],
    result_row_limit: int = _MAX_SUMMARY_ROWS,
) -> dict[str, Any]:
    """
    ``SELECT`` label columns and ``SUM`` of each value column from ``public.table_name``,
    ``GROUP BY`` all label columns. Column names are validated against the table; identifiers
    are passed through ``psycopg.sql.Identifier`` only.
    """
    if not (table_name or "").strip():
        raise ValueError("Table name required.")
    if not label_columns:
        raise ValueError("Select at least one label column (GROUP BY).")
    if not value_columns:
        raise ValueError("Select at least one value column to sum.")
    if len(label_columns) > _MAX_ANALYSIS_LABEL_COLS:
        raise ValueError(f"At most {_MAX_ANALYSIS_LABEL_COLS} label columns.")
    if len(value_columns) > _MAX_ANALYSIS_VALUE_COLS:
        raise ValueError(f"At most {_MAX_ANALYSIS_VALUE_COLS} value columns.")

    result_row_limit = max(1, min(int(result_row_limit), _MAX_SUMMARY_ROWS))

    tables = list_public_tables(
        host=host, port=port, user=user, password=password, dbname=dbname
    )
    by_lower = {t.lower(): t for t in tables}
    resolved_table = by_lower.get(table_name.strip().lower())
    if not resolved_table:
        raise ValueError("Table is not in the public schema list for this database.")

    allowed = list_table_columns(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=dbname,
        table_name=resolved_table,
    )
    col_lower = {c.lower(): c for c in allowed}

    def _resolve_cols(requested: list[str], role: str) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for raw in requested:
            key = (raw or "").strip()
            if not key:
                continue
            canon = col_lower.get(key.lower())
            if not canon:
                raise ValueError(f"Unknown {role} column for this table: {key!r}")
            if canon.lower() not in seen:
                seen.add(canon.lower())
                out.append(canon)
        return out

    resolved_labels = _resolve_cols(label_columns, "label")
    resolved_values = _resolve_cols(value_columns, "value")
    if not resolved_labels:
        raise ValueError("Select at least one label column (GROUP BY).")
    if not resolved_values:
        raise ValueError("Select at least one value column to sum.")

    label_set = {c.lower() for c in resolved_labels}
    overlap = [c for c in resolved_values if c.lower() in label_set]
    if overlap:
        raise ValueError(
            "Label and value column sets must not overlap: "
            + ", ".join(repr(c) for c in overlap)
        )

    select_exprs: list[sql.SQL] = [sql.SQL("{}").format(sql.Identifier(c)) for c in resolved_labels]
    for v in resolved_values:
        alias = f"sum_{v}"
        if len(alias) > 63:
            alias = alias[:63]
        select_exprs.append(
            sql.SQL("SUM({}) AS {}").format(
                sql.Identifier(v),
                sql.Identifier(alias),
            )
        )

    group_by = sql.SQL(", ").join(sql.Identifier(c) for c in resolved_labels)
    order_by = sql.SQL(", ").join(
        sql.SQL("{} ASC NULLS LAST").format(sql.Identifier(c)) for c in resolved_labels
    )

    stmt = sql.SQL("SELECT {} FROM {} GROUP BY {} ORDER BY {} LIMIT {}").format(
        sql.SQL(", ").join(select_exprs),
        sql.Identifier(resolved_table),
        group_by,
        order_by,
        sql.Literal(result_row_limit + 1),
    )

    with connect_with_params(
        host=host, port=port, user=user, password=password, dbname=dbname
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(stmt)
            colnames = [d.name for d in cur.description] if cur.description else []
            fetched = cur.fetchall()
    truncated = len(fetched) > result_row_limit
    fetched = fetched[:result_row_limit]

    def _json_friendly(v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, Decimal):
            return float(v)
        if isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, date):
            return v.isoformat()
        if isinstance(v, UUID):
            return str(v)
        if isinstance(v, (bytes, memoryview)):
            return None
        return v

    rows = []
    for row in fetched:
        rows.append({colnames[i]: _json_friendly(row[i]) for i in range(len(colnames))})
    return {
        "columns": colnames,
        "rows": rows,
        "truncated": truncated,
        "row_count": len(rows),
        "table": resolved_table,
        "database": (dbname or "").strip(),
    }
