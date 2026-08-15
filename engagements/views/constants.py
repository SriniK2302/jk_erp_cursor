_TEAM_ASSIGNMENT_REPORT_STATUS_FILTERS = frozenset({"current", "completed"})
_STATUS_REMARK_REPORT_LEVEL_FILTERS = frozenset(
    {"all", "engagement", "division", "work_area"}
)
_AUDIT_QUERY_EXPECTED_FILTERS = frozenset({"all", "internal", "client"})
_AUDIT_QUERY_STATUS_FILTERS = frozenset({"all", "open", "closed"})
_AUDIT_QUERY_TYPE_FILTERS = frozenset({"all", "query", "remark"})
_ENGAGEMENT_LIST_STATUS_FILTERS = frozenset(
    {"active", "all", "pending", "scheduled", "in_progress", "completed"}
)
_DIVISION_TEAM_LIST_FILTERS = frozenset({"all", "unassigned"})
_DIVISION_STATUS_LIST_FILTERS = frozenset({"active", "all"})
_WORK_AREA_STATUS_FILTERS = frozenset({"active", "all"})
_ENGAGEMENT_DIVISIONS_TEAM_SESSION_KEY = "engagement_divisions_team_filter"
_ENGAGEMENT_DIVISIONS_STATUS_SESSION_KEY = "engagement_divisions_status_filter"
ENGAGEMENTS_MODULE_GROUP = "module_engagements"
