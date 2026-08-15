"""Split engagements/views.py into engagements/views/ package."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source_lines = (ROOT / "engagements/views.py").read_text(encoding="utf-8").splitlines(
    keepends=True
)

STD_IMPORTS = "".join(source_lines[0:128])  # lines 1-128

chunks = [
    ("constants.py", 276, 282, ""),
    ("constants.py", 1248, 1257, ""),
    ("access.py", 1259, 1347, "from .constants import ENGAGEMENTS_MODULE_GROUP\n\n"),
    ("manage.py", 139, 147, ""),
    ("certification_fees.py", 148, 229, ""),
    ("session_views.py", 232, 274, ""),
    ("note_mail_helpers.py", 285, 402, ""),
    ("reports.py", 404, 1006, "from .constants import (\n"
     "    _AUDIT_QUERY_EXPECTED_FILTERS,\n"
     "    _AUDIT_QUERY_STATUS_FILTERS,\n"
     "    _AUDIT_QUERY_TYPE_FILTERS,\n"
     "    _STATUS_REMARK_REPORT_LEVEL_FILTERS,\n"
     "    _TEAM_ASSIGNMENT_REPORT_STATUS_FILTERS,\n"
     ")\n"
     "from .note_mail_helpers import _audit_query_mail_context\n\n"),
    ("bulk_team.py", 1009, 1131, ""),
    ("work_area_hub.py", 1134, 1245, "from .constants import _WORK_AREA_STATUS_FILTERS\n\n"),
    ("engagement_list.py", 1352, 1424, "from .constants import _ENGAGEMENT_LIST_STATUS_FILTERS\n\n"),
    ("engagement_crud.py", 1426, 1694, ""),
    ("work_area_bulk_helpers.py", 1696, 1964, ""),
    (
        "engagement_work_area_views.py",
        1966,
        2963,
        "from .work_area_bulk_helpers import (\n"
        "    _add_engagement_work_areas_from_service_templates,\n"
        "    _bulk_add_all_standard_work_areas,\n"
        "    _bulk_delete_work_areas_without_queries,\n"
        "    _engagement_service_work_area_pick_rows,\n"
        "    _json_bulk_work_areas_response,\n"
        "    _mappable_template_ids_not_on_scope,\n"
        "    _resequence_scoped_work_areas,\n"
        "    _service_checklist_templates_for_service,\n"
        ")\n"
        "from .constants import _WORK_AREA_STATUS_FILTERS\n\n",
    ),
    (
        "division_work_area_views.py",
        2965,
        4038,
        "from .work_area_bulk_helpers import (\n"
        "    _add_division_work_areas_from_service_templates,\n"
        "    _bulk_add_all_standard_work_areas,\n"
        "    _bulk_delete_work_areas_without_queries,\n"
        "    _division_service_work_area_pick_rows,\n"
        "    _json_bulk_work_areas_response,\n"
        "    _mappable_template_ids_not_on_scope,\n"
        "    _resequence_scoped_work_areas,\n"
        "    _service_checklist_templates_for_service,\n"
        ")\n"
        "from .constants import _WORK_AREA_STATUS_FILTERS\n\n",
    ),
    ("documentation_views.py", 4040, 5054, ""),
    ("division_views.py", 5057, 5721, "from .constants import (\n"
     "    _DIVISION_STATUS_LIST_FILTERS,\n"
     "    _DIVISION_TEAM_LIST_FILTERS,\n"
     "    _ENGAGEMENT_DIVISIONS_STATUS_SESSION_KEY,\n"
     "    _ENGAGEMENT_DIVISIONS_TEAM_SESSION_KEY,\n"
     ")\n\n"),
]

ACCESS_IMPORT = """from .access import (
    _active_time_session_for_user,
    _can_manage_structure,
    _division_work_area_queryset_for_user,
    _engagement_division_queryset_for_user,
    _engagement_queryset_for_user,
    _engagement_work_area_queryset_for_user,
    _has_engagements_module_access,
    _timer_scope_dict,
)

"""

out_dir = ROOT / "engagements/views"
out_dir.mkdir(exist_ok=True)

# _std_imports.py — shared third-party / app imports (no view cross-imports)
(out_dir / "_std_imports.py").write_text(STD_IMPORTS, encoding="utf-8")
print("wrote _std_imports.py")

file_bodies: dict[str, str] = {}

for item in chunks:
    fname, start, end, extra = item
    body = "".join(source_lines[start - 1 : end])
    if fname == "constants.py":
        if fname not in file_bodies:
            file_bodies[fname] = ""
        file_bodies[fname] += body
        continue
    prefix = "from engagements.views._std_imports import *  # noqa: F403\n\n"
    if fname != "access.py" and fname != "constants.py":
        prefix += ACCESS_IMPORT
    if extra:
        prefix += extra
    content = prefix + body
    if not content.endswith("\n"):
        content += "\n"
    file_bodies[fname] = content

# constants.py — ENGAGEMENTS_MODULE_GROUP + filter constants
constants_body = file_bodies.get("constants.py", "")
constants_content = (
    constants_body
    + "\nENGAGEMENTS_MODULE_GROUP = \"module_engagements\"\n"
)
(out_dir / "constants.py").write_text(constants_content, encoding="utf-8")
print("wrote constants.py")

for fname, content in file_bodies.items():
    if fname == "constants.py":
        continue
    (out_dir / fname).write_text(content, encoding="utf-8")
    print("wrote", fname)

# Fix access.py — use constants for ENGAGEMENTS_MODULE_GROUP (already in prefix)
access_content = file_bodies["access.py"]
if "ENGAGEMENTS_MODULE_GROUP" not in access_content.split("def _has")[0]:
    access_content = access_content.replace(
        "from .constants import ENGAGEMENTS_MODULE_GROUP\n\n",
        "from .constants import ENGAGEMENTS_MODULE_GROUP\n\n",
    )
(out_dir / "access.py").write_text(access_content, encoding="utf-8")

init = '''"""Engagement views package — re-exports for URLconf and external imports."""

from .access import (
    _active_time_session_for_user,
    _can_manage_structure,
    _division_work_area_queryset_for_user,
    _engagement_division_queryset_for_user,
    _engagement_queryset_for_user,
    _engagement_work_area_queryset_for_user,
    _has_engagements_module_access,
    _timer_scope_dict,
)
from .bulk_team import bulk_engagement_team_assignments
from .certification_fees import (
    certification_fee_create,
    certification_fee_edit,
    certification_fees,
)
from .division_views import (
    engagement_division_create,
    engagement_division_documentation_attachment_download,
    engagement_division_documentation_map_create,
    engagement_division_documentation_map_edit,
    engagement_division_documentation_map_files,
    engagement_division_documentation_maps,
    engagement_division_documentation_option_search,
    engagement_division_edit,
    engagement_division_team_assignment_create,
    engagement_division_team_assignment_edit,
    engagement_division_team_assignments,
    engagement_division_uploaded_documents_report,
    engagement_divisions,
    engagement_schedule_bounds_json,
)
from .division_work_area_views import (
    engagement_division_status_remarks,
    engagement_division_work_area_assignment_create,
    engagement_division_work_area_assignment_edit,
    engagement_division_work_area_assignments,
    engagement_division_work_area_create,
    engagement_division_work_area_document_download,
    engagement_division_work_area_documents,
    engagement_division_work_area_edit,
    engagement_division_work_area_notes_list,
    engagement_division_work_area_queries,
    engagement_division_work_area_schedule,
    engagement_division_work_area_schedule_create,
    engagement_division_work_area_schedule_edit,
    engagement_division_work_area_status_remarks,
    engagement_division_work_areas,
    engagement_division_query_attachment_download,
    engagement_status_remarks,
    engagement_work_area_status_remarks,
)
from .documentation_views import (
    engagement_documentation_attachment_download,
    engagement_documentation_map_create,
    engagement_documentation_map_edit,
    engagement_documentation_map_files,
    engagement_documentation_map_word_filled_download,
    engagement_documentation_maps,
    engagement_documentation_missing_uploads_report,
    engagement_documentation_option_search,
    engagement_documents_and_notes,
    engagement_uploaded_documents_report,
)
from .engagement_crud import (
    engagement_create,
    engagement_edit,
    engagement_schedule_create,
    engagement_schedule_edit,
    engagement_schedules,
    engagement_team_assignment_create,
    engagement_team_assignment_edit,
    engagement_team_assignments,
)
from .engagement_list import engagements
from .engagement_work_area_views import (
    engagement_all_work_area_notes,
    engagement_query_attachment_download,
    engagement_work_area_assignment_create,
    engagement_work_area_assignment_edit,
    engagement_work_area_assignments,
    engagement_work_area_create,
    engagement_work_area_document_download,
    engagement_work_area_documents,
    engagement_work_area_edit,
    engagement_work_area_notes_list,
    engagement_work_area_queries,
    engagement_work_area_schedule,
    engagement_work_area_schedule_create,
    engagement_work_area_schedule_edit,
    engagement_work_areas,
)
from .manage import manage_engagements
from .reports import (
    audit_queries_report,
    audit_query_open_draft,
    status_remarks_report,
    team_assignments_report,
    work_area_notes_report,
)
from .session_views import session_engagement_clear, session_engagement_set
from .work_area_hub import (
    work_area_hub,
    work_area_pick_division,
    work_area_pick_engagement,
)

__all__ = [name for name in dir() if not name.startswith("_") or name.startswith("__")]
'''
(out_dir / "__init__.py").write_text(init, encoding="utf-8")
print("wrote __init__.py")
