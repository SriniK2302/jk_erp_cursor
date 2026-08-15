"""Engagement views package — re-exports for URLconf and external imports."""

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
    engagement_division_uploaded_documents_report,
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
