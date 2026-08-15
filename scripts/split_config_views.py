"""Split config/views.py into config/views/ package."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source_lines = (ROOT / "config/views.py").read_text(encoding="utf-8").splitlines(
    keepends=True
)

STD_IMPORTS = "".join(source_lines[0:52]).replace(
    "from .forms import", "from config.forms import"
)

ACCESS_IMPORT = """from .access import (
    _engagement_queryset_for_user,
    _has_module_access,
)
from .constants import MODULE_ENGAGEMENTS, MODULE_SETUP, MODULE_TOOLS

"""

UTILITY_JOBS_IMPORT = "from .utility_jobs import *  # noqa: F403\n\n"

chunks = [
    ("constants.py", 63, 65, "", False),
    (
        "access.py",
        68,
        88,
        "from .constants import MODULE_ENGAGEMENTS, MODULE_SETUP, MODULE_TOOLS\n\n",
        False,
    ),
    ("utility_jobs.py", 54, 61, "", True),
    ("utility_jobs.py", 275, 669, "", True),
    (
        "home_helpers.py",
        90,
        273,
        "from .access import _engagement_queryset_for_user\n\n",
        True,
    ),
    ("todos.py", 671, 750, "", True),
    (
        "home.py",
        752,
        798,
        "from .access import _has_module_access\n"
        "from .constants import MODULE_ENGAGEMENTS, MODULE_SETUP, MODULE_TOOLS\n"
        "from .home_helpers import _home_work_list_rows\n\n",
        True,
    ),
    ("setup_gl.py", 800, 1020, ACCESS_IMPORT, True),
    ("data_utilities.py", 1022, 1727, ACCESS_IMPORT + UTILITY_JOBS_IMPORT, True),
    ("utilities.py", 1729, 3011, ACCESS_IMPORT + UTILITY_JOBS_IMPORT, True),
]

out_dir = ROOT / "config/views"
out_dir.mkdir(exist_ok=True)

(out_dir / "_std_imports.py").write_text(STD_IMPORTS, encoding="utf-8")
print("wrote _std_imports.py")

append_bodies: dict[str, str] = {"utility_jobs.py": ""}
file_bodies: dict[str, str] = {}

for fname, start, end, extra, use_access in chunks:
    body = "".join(source_lines[start - 1 : end])
    if fname == "utility_jobs.py":
        append_bodies[fname] += body
        continue
    if fname == "constants.py":
        file_bodies[fname] = body
        continue
    prefix = "from config.views._std_imports import *  # noqa: F403\n\n"
    if use_access and fname not in {"home.py", "home_helpers.py", "todos.py"} and not extra:
        prefix += ACCESS_IMPORT
    if extra:
        prefix += extra
    content = prefix + body
    if not content.endswith("\n"):
        content += "\n"
    file_bodies[fname] = content

utility_jobs_content = (
    "from config.views._std_imports import *  # noqa: F403\n\n"
    + append_bodies["utility_jobs.py"]
)
(out_dir / "utility_jobs.py").write_text(utility_jobs_content, encoding="utf-8")
print("wrote utility_jobs.py")

(out_dir / "constants.py").write_text(file_bodies["constants.py"], encoding="utf-8")
print("wrote constants.py")

for fname, content in file_bodies.items():
    if fname == "constants.py":
        continue
    if fname == "todos.py":
        content = content.replace("from .models import", "from config.models import")
    if fname == "setup_gl.py":
        content = content.replace("from .models import", "from config.models import")
    (out_dir / fname).write_text(content, encoding="utf-8")
    print("wrote", fname)

init = '''"""Config views package — re-exports for URLconf and external imports."""

from .access import _engagement_queryset_for_user, _has_module_access
from .constants import MODULE_ENGAGEMENTS, MODULE_SETUP, MODULE_TOOLS
from .data_utilities import (
    create_table_run,
    create_table_sheets_json,
    data_analysis,
    data_analysis_summary_json,
    data_create_table,
    data_excel_import,
    data_pg_row_delete,
    data_utilities,
    excel_import_headers_json,
    excel_import_match_report,
    excel_import_run,
    excel_import_sheets_json,
    excel_import_start,
    excel_import_status,
    pg_list_databases_json,
    pg_list_databases_settings_json,
    pg_row_delete_columns_json,
    pg_row_delete_execute,
    pg_row_delete_tables_json,
    pg_row_delete_test_json,
    select_create_table_excel_file,
    select_excel_import_file,
    tools_utilities,
)
from .home import admin_technical_data_flow, home, setup
from .setup_gl import (
    gl_hub,
    gl_trial_balance,
    sales_ledger_settings,
    setup_mail_settings,
)
from .todos import (
    my_todo_create,
    my_todo_delete,
    my_todo_edit,
    my_todo_toggle,
    my_todos,
)
from .utilities import (
    audit_document_renaming_filing,
    audit_document_triage,
    audit_triage_move,
    audit_triage_scan,
    delete_duplicate_files,
    delete_empty_folders,
    duplicate_delete_status,
    file_content_search,
    find_similar_files,
    move_files_name_contains,
    move_files_to_fy_folder,
    organize_files_fy_move_tool,
    organize_files_utilities,
    rename_date_prefix_files,
    rename_files_based_on_text,
    rename_files_by_content_date,
    rename_files_date_prefix_tool,
    rename_files_text_tool,
    rename_files_utilities,
    select_audit_triage_dest,
    select_audit_triage_source,
    select_content_search_folder,
    select_duplicate_source_folder,
    select_duplicate_target_folder,
    select_folder_for_delete_empty,
    select_move_name_search_folder,
    select_move_name_target_folder,
    select_move_to_fy_folder,
    select_rename_content_date_folder,
    select_rename_date_prefix_folder,
    select_rename_text_folder,
    select_similar_files_folder,
    select_similar_reference_file,
    similar_files_page,
    similar_files_report_start,
    similar_files_report_status,
    similar_files_status,
    utilities,
)

__all__ = [name for name in dir() if not name.startswith("_") or name.startswith("__")]
'''
(out_dir / "__init__.py").write_text(init, encoding="utf-8")
print("wrote __init__.py")
