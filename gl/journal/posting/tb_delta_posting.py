"""Apply cumulative TB snapshots for one authorised header (domain-agnostic)."""

from __future__ import annotations

from ..models import GlHeader
from ..tb_sync import apply_tb_delta_for_gl_header


class GlTbDeltaPosting:
    """Updates ``tb_table`` / ``tb_table_month`` for a voucher already marked Authorised."""

    def execute(self, *, header: GlHeader) -> None:
        apply_tb_delta_for_gl_header(header)
