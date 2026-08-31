from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Case, F, IntegerField, Min, Q, Sum, Value, When
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from pathlib import Path
import threading
import time
import uuid

from hr.teams.models import (
    TeamMember,
)
from utilities.delete_duplicate_files import move_duplicate_files_by_signature
from utilities.delete_empty_folders import choose_root_folder, delete_empty_folders_under
from utilities.file_content_search import scan_folder_for_phrase
from utilities.move_all_files import move_all_files_flat
from utilities.move_files_to_fy_folder import move_direct_files_to_fy_folders
from utilities.move_files_by_name_contains import move_direct_files_name_contains
from utilities.move_files_by_first_chars import move_direct_files_by_first_chars
from utilities.prefix_fy_from_tax_files import prefix_fy_from_tax_files
from utilities.rename_files_by_content_date import rename_direct_files_by_content_date
from utilities.rename_date_prefix_files import rename_direct_files_date_prefix
from utilities.rename_files_based_on_text import rename_direct_files_by_text
from utilities.cleanup_fy_duplicate_refs import cleanup_fy_duplicate_refs
from utilities.similar_files import (
    choose_spreadsheet_file,
    find_similar_spreadsheet_files,
    find_similar_to_reference_file,
)


from utilities.excel_to_postgres import (
    choose_excel_file,
    create_public_table_from_schema_sheet,
    inspect_import_column_mapping,
    import_sheet_to_postgres,
    list_sheet_names,
    read_sheet_headers_only,
)
from utilities.pg_row_delete import (
    delete_rows_public,
    list_database_names,
    list_public_tables,
    list_table_columns,
    summarize_public_table_group_by,
    test_pg_connection,
)

from engagements.models import Engagement, STATUS_IN_PROGRESS, STATUS_SCHEDULED
from hr.teams.models import TeamMember

from config.forms import SalesLedgerSettingsForm, SmtpMailSettingsForm, UserTodoForm
