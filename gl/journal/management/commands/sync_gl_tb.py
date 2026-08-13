from django.core.management.base import BaseCommand

from gl.journal.tb_sync import (
    rebuild_tb_table_from_gl_lines,
    rebuild_tb_table_month_from_gl_lines,
)


class Command(BaseCommand):
    help = "Rebuild tb_table and tb_table_month from all authorised GL lines."

    def handle(self, *args, **options):
        n = rebuild_tb_table_from_gl_lines()
        m = rebuild_tb_table_month_from_gl_lines()
        self.stdout.write(self.style.SUCCESS(f"tb_table rebuilt: {n} row(s)."))
        self.stdout.write(self.style.SUCCESS(f"tb_table_month rebuilt: {m} row(s)."))
