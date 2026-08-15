from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError
from django.db.models import Count, Exists, F, Max, Min, OuterRef, Prefetch, Q
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.dateparse import parse_date
from django.utils.text import get_valid_filename
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import io
import json
import logging
import re
from urllib.parse import urlencode, quote

from sales.client_classifications.models import ClientClassification
from hr.teams.models import TeamMember

from engagements.documentations.word_template import word_template_content_type
from engagements.documentations.representation_matrix import (
    is_mr02_documentation,
    mr02_point_rows,
    parse_representation_matrix_post,
    REPRESENTATION_POINT_STATUS_CHOICES,
)
from engagements.documentations.word_template_fill import (
    fill_docx_template,
    filled_engagement_documentation_docx_filename,
    list_unresolved_tokens_in_document_xml,
    merge_context_for_engagement,
)

from engagements import team_mail
from engagements.forms import (
    DivisionWorkAreaTeamAssignmentForm,
    _engagement_schedule_bounds,
    EngagementDivisionForm,
    EngagementDivisionDocumentationMapForm,
    EngagementDivisionTeamAssignmentForm,
    EngagementDocumentationMapForm,
    EngagementForm,
    EngagementWorkAreaTeamAssignmentForm,
    DivisionWorkAreaForm,
    DivisionWorkAreaPeriodForm,
    EngagementScheduleForm,
    EngagementTeamAssignmentForm,
    EngagementWorkAreaForm,
    EngagementWorkAreaPeriodForm,
    filter_engagement_documentation_by_client_classification,
)
from engagements.models import (
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_PENDING,
    STATUS_SCHEDULED,
    Engagement,
    EngagementDivision,
    EngagementDivisionDocumentationMap,
    EngagementDivisionDocumentationMapAttachment,
    EngagementDivisionTeamAssignment,
    EngagementDocumentation,
    EngagementDocumentationMap,
    EngagementDocumentationMapAttachment,
    EngagementTeamAssignment,
    DivisionWorkArea,
    DivisionWorkAreaPeriod,
    DivisionWorkAreaDocument,
    AuditQuery,
    AuditQueryAttachment,
    WorkDocument,
    AuditQueryMailDraftLog,
    AuditQueryResponse,
    DivisionWorkAreaStatusRemark,
    DivisionWorkAreaTeamAssignment,
    EngagementDivisionStatusRemark,
    EngagementSchedule,
    EngagementStatusRemark,
    EngagementWorkArea,
    EngagementWorkAreaStatusRemark,
    EngagementWorkAreaTeamAssignment,
    EngagementWorkAreaDocument,
    EngagementWorkAreaPeriod,
    ServiceEngagementChecklistWorkArea,
)
from engagements.closure import assert_division_open_for_management, assert_engagement_open_for_management
from engagements.session_context import (
    engagement_ids_for_lists,
    engagement_select_label,
    clear_session_engagement,
    filter_by_engagement_id,
    filter_engagement_queryset,
    set_session_engagement,
)
from engagements.work_area_notes_batch import (
    batch_save_wants_json,
    checklist_items_queryset,
    add_all_checklist_lines_to_notes_log,
    json_batch_save_response,
    save_work_area_notes_batch,
    save_work_area_notes_batch_single_row,
    work_area_has_checklist_template,
    work_area_notes_list_page_context,
    work_area_notes_page_context,
)
from engagements.timesheets.models import TimeSession
from engagements.timesheets.views import (
    my_time_log,
    timer_recent_tasks,
    timer_start_division,
    timer_start_division_work_area,
    timer_start_engagement,
    timer_start_engagement_work_area,
    timer_stop,
)
