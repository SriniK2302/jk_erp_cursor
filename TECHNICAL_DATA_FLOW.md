# JK ERP Data Flow Reference

This document is the central technical reference for data flow in the Engagements module.
It focuses on how data moves across UI -> view -> form/model -> database, and where transaction
boundaries are applied for safety.

## 1) Scope

Primary area covered:

- `engagements/views.py`
- `engagements/forms.py`
- `engagements/models.py`
- `engagements/urls.py`
- `templates/engagements/*`

Functional scope:

- Engagements and divisions
- Work areas and work area schedules
- Documentation mapping
- File attachments/documents
- Uploaded document reporting and duplicate handling

## 2) Core Data Entities

High-level entities involved in flow:

- Engagement hierarchy
  - `Engagement`
  - `EngagementDivision`
  - `EngagementWorkArea`
  - `DivisionWorkArea`
  - `EngagementWorkAreaPeriod`
  - `DivisionWorkAreaPeriod`
- Documentation setup and mapping
  - `EngagementDocumentation` (master setup)
  - `EngagementDocumentationMap` (engagement mapping)
  - `EngagementDivisionDocumentationMap` (division mapping)
- Uploaded files
  - `EngagementDocumentationMapAttachment`
  - `EngagementDivisionDocumentationMapAttachment`
  - `EngagementWorkAreaDocument`
  - `DivisionWorkAreaDocument`

## 3) Request/Data Flow Pattern

Most flows use this pattern:

1. Route in `engagements/urls.py`
2. View in `engagements/views.py`
3. Optional validation in `engagements/forms.py`
4. ORM writes/reads in models
5. Render via `templates/engagements/*.html`

For write actions:

- `POST` branch handles create/update/delete operations
- success/failure feedback via Django messages
- redirect-after-post to avoid duplicate form submissions

For report/list actions:

- `GET` branch builds rows from one or more models
- rows are sorted and rendered in grid templates

## 4) Major Flows

### 4.1 Work Area Ordering

Used in engagement and division work area create/edit:

- helper: `_resequence_scoped_work_areas(...)`
- selected item is inserted at requested sort position
- all sibling rows are renumbered sequentially

Result:

- no duplicate sort order within same scope
- contiguous ordering (`1..n`)

### 4.2 Copy Work Areas from Another Division

Action:

- `engagement_division_work_areas` with `action=copy_from_division`

Behavior:

- source options filtered by same:
  - client
  - service
  - fiscal year
- copies only missing names (case-insensitive dedupe)
- resequences final sort order after insertion

### 4.3 Documentation Mapping

Engagement-level and division-level mapping flows support:

- single add/edit
- multi-select add (bulk create)
- engagement prefill based on client classification

### 4.4 Uploaded Documents Reports

Reports:

- Engagement-wide uploaded report
- Division uploaded report

Rows aggregate documents from multiple sources and expose:

- document date
- source information
- document label
- file link
- duplicate/delete action status

Duplicate detection:

- Division report: duplicates grouped by normalized `file_name`
- Engagement report: duplicates grouped by `(division_scope, file_name)`
  - prevents false duplicates across different divisions

## 5) Transaction Safety (Atomic Boundaries)

The module uses `transaction.atomic()` for write-heavy flows that touch multiple rows/tables.

### Atomic-protected flows

- Work area create/edit plus resequencing
  - `_engagement_work_area_form_view`
  - `_division_work_area_form_view`
- Division copy-from-division operation
  - `engagement_division_work_areas` (`copy_from_division`)
- Work area schedule save with optional engagement schedule backfill
  - `_engagement_work_area_schedule_form_view`
  - `_division_work_area_schedule_form_view`
- Bulk documentation mapping operations
  - `engagement_documentation_maps` prefill action
  - `_engagement_documentation_map_form_view` bulk/single save paths
  - `_engagement_division_documentation_map_form_view` bulk/single save paths
- Multi-file upload actions
  - `engagement_work_area_documents` upload path
  - `engagement_division_work_area_documents` upload path
  - `engagement_documentation_map_files` upload path
  - `engagement_division_documentation_map_files` upload path

### Why this matters

If a later step fails inside an atomic block, Django rolls back all changes in that block.
This avoids partial write states (for example: item created but resequencing not completed).

## 6) Delete Flows and Scope Safety

Delete actions are scope-constrained in queryset filters to prevent accidental cross-scope deletes.

Examples:

- duplicate delete in reports validates ownership by engagement/division scope
- map/attachment/document deletes always filter by parent object from URL context

## 7) UI/Template Conventions Used

- Grid/list pages use `data-grid` + search toolbar pattern
- post actions use hidden `action` field
- sticky right-side action column via `col-actions`
- uploaded reports use compact combined duplicate/action column (`Dup/Action`)
- refresh button available in report toolbar

## 8) Operational Notes

- After model field changes, always run migrations before using new values.
- For write flows involving loops/bulk actions, prefer a single atomic unit.
- Keep duplicate criteria explicit and business-driven (currently file-name based with engagement
  report division scoping).

## 9) Suggested Future Enhancements

- Add a "show only duplicates" filter in reports.
- Add configurable duplicate strategy (file name only vs hash/content check).
- Add periodic cleanup job for aged duplicates with review mode.
- Expand this doc with sequence diagrams if architecture scope grows.

