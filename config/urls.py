"""
URL configuration for config project.
"""

from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.views.generic import RedirectView
from django.urls import include, path

from admin import views as admin_views
from . import views

urlpatterns = [
    path(
        "admin/technical-data-flow/",
        views.admin_technical_data_flow,
        name="admin_technical_data_flow",
    ),
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path("my-todos/", views.my_todos, name="my_todos"),
    path("my-todos/new/", views.my_todo_create, name="my_todo_create"),
    path("my-todos/<int:pk>/edit/", views.my_todo_edit, name="my_todo_edit"),
    path("my-todos/<int:pk>/delete/", views.my_todo_delete, name="my_todo_delete"),
    path("my-todos/<int:pk>/toggle/", views.my_todo_toggle, name="my_todo_toggle"),
    path('engagements/', include('engagements.urls')),
    path('invoices/', include('sales.invoices.urls')),
    path('setup/', views.setup, name='setup'),
    path('gl/', views.gl_hub, name='gl_hub'),
    path('gl/trial-balance/', views.gl_trial_balance, name='gl_trial_balance'),
    path('setup/chart-of-accounts/', include('gl.chart_of_accounts.urls')),
    path(
        'setup/mail-settings/',
        views.setup_mail_settings,
        name='setup_mail_settings',
    ),
    path('data-utilities/', views.data_utilities, name='data_utilities'),
    path('tools-utilities/', views.tools_utilities, name='tools_utilities'),
    path(
        'data-utilities/data-analysis/',
        views.data_analysis,
        name='data_analysis',
    ),
    path(
        'data-utilities/data-analysis/summary/',
        views.data_analysis_summary_json,
        name='data_analysis_summary_json',
    ),
    path(
        'data-utilities/create-table/select-file/',
        views.select_create_table_excel_file,
        name='select_create_table_excel_file',
    ),
    path(
        'data-utilities/create-table/sheets/',
        views.create_table_sheets_json,
        name='create_table_sheets_json',
    ),
    path(
        'data-utilities/create-table/run/',
        views.create_table_run,
        name='create_table_run',
    ),
    path(
        'data-utilities/create-table/',
        views.data_create_table,
        name='data_create_table',
    ),
    path('data-utilities/excel-import/', views.data_excel_import, name='data_excel_import'),
    path(
        'data-utilities/excel-import/select-file/',
        views.select_excel_import_file,
        name='select_excel_import_file',
    ),
    path(
        'data-utilities/excel-import/sheets/',
        views.excel_import_sheets_json,
        name='excel_import_sheets_json',
    ),
    path(
        'data-utilities/excel-import/headers/',
        views.excel_import_headers_json,
        name='excel_import_headers_json',
    ),
    path(
        'data-utilities/excel-import/match-report/',
        views.excel_import_match_report,
        name='excel_import_match_report',
    ),
    path(
        'data-utilities/excel-import/run/',
        views.excel_import_run,
        name='excel_import_run',
    ),
    path(
        'data-utilities/excel-import/start/',
        views.excel_import_start,
        name='excel_import_start',
    ),
    path(
        'data-utilities/excel-import/status/<str:job_id>/',
        views.excel_import_status,
        name='excel_import_status',
    ),
    path(
        'data-utilities/pg-delete-rows/',
        views.data_pg_row_delete,
        name='data_pg_row_delete',
    ),
    path(
        'data-utilities/pg-delete-rows/test/',
        views.pg_row_delete_test_json,
        name='pg_row_delete_test_json',
    ),
    path(
        'data-utilities/pg-list-databases/',
        views.pg_list_databases_json,
        name='pg_list_databases_json',
    ),
    path(
        'data-utilities/pg-list-databases-settings/',
        views.pg_list_databases_settings_json,
        name='pg_list_databases_settings_json',
    ),
    path(
        'data-utilities/pg-delete-rows/tables/',
        views.pg_row_delete_tables_json,
        name='pg_row_delete_tables_json',
    ),
    path(
        'data-utilities/pg-delete-rows/columns/',
        views.pg_row_delete_columns_json,
        name='pg_row_delete_columns_json',
    ),
    path(
        'data-utilities/pg-delete-rows/execute/',
        views.pg_row_delete_execute,
        name='pg_row_delete_execute',
    ),
    path('utilities/', views.utilities, name='utilities'),
    path(
        'utilities/rename-files/',
        views.rename_files_utilities,
        name='rename_files_utilities',
    ),
    path(
        'utilities/rename-files/date-prefix/',
        views.rename_files_date_prefix_tool,
        name='rename_files_date_prefix_tool',
    ),
    path(
        'utilities/rename-files/text/',
        views.rename_files_text_tool,
        name='rename_files_text_tool',
    ),
    path(
        'utilities/organize-files/',
        views.organize_files_utilities,
        name='organize_files_utilities',
    ),
    path(
        'utilities/organize-files/fy-move/',
        views.organize_files_fy_move_tool,
        name='organize_files_fy_move_tool',
    ),
    path(
        'utilities/audit-document-renaming-filing/',
        views.audit_document_renaming_filing,
        name='audit_document_renaming_filing',
    ),
    path(
        'utilities/audit-document-triage/',
        views.audit_document_triage,
        name='audit_document_triage',
    ),
    path(
        'utilities/audit-triage-scan/',
        views.audit_triage_scan,
        name='audit_triage_scan',
    ),
    path(
        'utilities/audit-triage-move/',
        views.audit_triage_move,
        name='audit_triage_move',
    ),
    path(
        'utilities/select-audit-triage-source/',
        views.select_audit_triage_source,
        name='select_audit_triage_source',
    ),
    path(
        'utilities/select-audit-triage-dest/',
        views.select_audit_triage_dest,
        name='select_audit_triage_dest',
    ),
    path('utilities/similar-files/', views.similar_files_page, name='similar_files_page'),
    path(
        'utilities/select-folder/',
        views.select_folder_for_delete_empty,
        name='select_folder_for_delete_empty',
    ),
    path(
        'utilities/select-duplicate-source-folder/',
        views.select_duplicate_source_folder,
        name='select_duplicate_source_folder',
    ),
    path(
        'utilities/select-duplicate-target-folder/',
        views.select_duplicate_target_folder,
        name='select_duplicate_target_folder',
    ),
    path(
        'utilities/select-content-search-folder/',
        views.select_content_search_folder,
        name='select_content_search_folder',
    ),
    path(
        'utilities/select-rename-date-prefix-folder/',
        views.select_rename_date_prefix_folder,
        name='select_rename_date_prefix_folder',
    ),
    path(
        'utilities/select-rename-text-folder/',
        views.select_rename_text_folder,
        name='select_rename_text_folder',
    ),
    path(
        'utilities/select-rename-content-date-folder/',
        views.select_rename_content_date_folder,
        name='select_rename_content_date_folder',
    ),
    path(
        'utilities/select-move-to-fy-folder/',
        views.select_move_to_fy_folder,
        name='select_move_to_fy_folder',
    ),
    path(
        'utilities/select-move-name-search-folder/',
        views.select_move_name_search_folder,
        name='select_move_name_search_folder',
    ),
    path(
        'utilities/select-move-name-target-folder/',
        views.select_move_name_target_folder,
        name='select_move_name_target_folder',
    ),
    path(
        'utilities/select-similar-files-folder/',
        views.select_similar_files_folder,
        name='select_similar_files_folder',
    ),
    path(
        'utilities/similar-files/select-reference/',
        views.select_similar_reference_file,
        name='select_similar_reference_file',
    ),
    path(
        'utilities/delete-empty-folders/',
        views.delete_empty_folders,
        name='delete_empty_folders',
    ),
    path(
        'utilities/file-content-search/',
        views.file_content_search,
        name='file_content_search',
    ),
    path(
        'utilities/rename-date-prefix-files/',
        views.rename_date_prefix_files,
        name='rename_date_prefix_files',
    ),
    path(
        'utilities/rename-files-based-on-text/',
        views.rename_files_based_on_text,
        name='rename_files_based_on_text',
    ),
    path(
        'utilities/rename-files-by-content-date/',
        views.rename_files_by_content_date,
        name='rename_files_by_content_date',
    ),
    path(
        'utilities/move-files-to-fy-folder/',
        views.move_files_to_fy_folder,
        name='move_files_to_fy_folder',
    ),
    path(
        'utilities/move-files-name-contains/',
        views.move_files_name_contains,
        name='move_files_name_contains',
    ),
    path(
        'utilities/delete-duplicate-files/',
        views.delete_duplicate_files,
        name='delete_duplicate_files',
    ),
    path(
        'utilities/delete-duplicate-files/status/<str:job_id>/',
        views.duplicate_delete_status,
        name='duplicate_delete_status',
    ),
    path(
        'utilities/similar-files/find/',
        views.find_similar_files,
        name='find_similar_files',
    ),
    path(
        'utilities/similar-files/status/<str:job_id>/',
        views.similar_files_status,
        name='similar_files_status',
    ),
    path(
        'utilities/similar-files/report/start/',
        views.similar_files_report_start,
        name='similar_files_report_start',
    ),
    path(
        'utilities/similar-files/report/status/<str:job_id>/',
        views.similar_files_report_status,
        name='similar_files_report_status',
    ),
    path('setup/users/', admin_views.setup_users, name='setup_users'),
    path('setup/users/<int:pk>/edit/', admin_views.setup_user_edit, name='setup_user_edit'),
    path(
        'setup/api/team-members/search/',
        admin_views.team_member_search_json,
        name='team_member_search',
    ),
    path('setup/sales/clients/', include('sales.clients.urls')),
    path(
        'setup/sales/client-classifications/',
        include('sales.client_classifications.urls'),
    ),
    path('setup/sales/services/', include('sales.services.urls')),
    path('setup/sales/udins-source/', include('sales.udins_source.urls')),
    path('setup/sales/udins/', include('sales.udins.urls')),
    path(
        'setup/sales/sales-ledger-settings/',
        views.sales_ledger_settings,
        name='sales_ledger_settings',
    ),
    path('setup/gl/fiscal-years/', include('gl.fiscal_years.urls')),
    path('setup/hr/teams/', include('hr.teams.urls')),
    path(
        'setup/hr/team-qualification-maps/',
        include('hr.team_qualification_maps.urls'),
    ),
    path('setup/hr/team-grade-maps/', include('hr.team_grade_maps.urls')),
    path('setup/hr/grades/', include('hr.grades.urls')),
    path('setup/hr/qualifications/', include('hr.qualifications.urls')),
    path(
        'setup/client-classifications/',
        RedirectView.as_view(
            url='/setup/sales/client-classifications/',
            permanent=False,
        ),
    ),
    path(
        'setup/sales/clients/classifications/',
        RedirectView.as_view(
            url='/setup/sales/client-classifications/',
            permanent=False,
        ),
    ),
    path(
        'setup/sales/clients/classifications/new/',
        RedirectView.as_view(
            url='/setup/sales/client-classifications/new/',
            permanent=False,
        ),
    ),
    path(
        'setup/sales/clients/classifications/<int:pk>/edit/',
        RedirectView.as_view(
            url='/setup/sales/client-classifications/%(pk)s/edit/',
            permanent=False,
        ),
    ),
    path(
        'setup/clients/',
        RedirectView.as_view(url='/setup/sales/clients/', permanent=False),
    ),
    path(
        'setup/services/',
        RedirectView.as_view(url='/setup/sales/services/', permanent=False),
    ),
    path(
        'setup/fiscal-years/',
        RedirectView.as_view(url='/setup/gl/fiscal-years/', permanent=False),
    ),
    path(
        'setup/teams/',
        RedirectView.as_view(url='/setup/hr/teams/', permanent=False),
    ),
    path(
        'setup/team-grade-maps/',
        RedirectView.as_view(
            url='/setup/hr/team-grade-maps/',
            permanent=False,
        ),
    ),
    path(
        'setup/team-qualification-maps/',
        RedirectView.as_view(
            url='/setup/hr/team-qualification-maps/',
            permanent=False,
        ),
    ),
    path(
        'setup/hr/teams/grade-maps/',
        RedirectView.as_view(
            url='/setup/hr/team-grade-maps/',
            permanent=False,
        ),
    ),
    path(
        'setup/hr/teams/grade-maps/new/',
        RedirectView.as_view(
            url='/setup/hr/team-grade-maps/new/',
            permanent=False,
        ),
    ),
    path(
        'setup/hr/teams/grade-maps/<int:pk>/edit/',
        RedirectView.as_view(
            url='/setup/hr/team-grade-maps/%(pk)s/edit/',
            permanent=False,
        ),
    ),
    path(
        'setup/hr/teams/grade-maps/defaults/',
        RedirectView.as_view(
            url='/setup/hr/team-grade-maps/defaults/',
            permanent=False,
        ),
    ),
    path(
        'setup/hr/teams/qualification-maps/',
        RedirectView.as_view(
            url='/setup/hr/team-qualification-maps/',
            permanent=False,
        ),
    ),
    path(
        'setup/hr/teams/qualification-maps/new/',
        RedirectView.as_view(
            url='/setup/hr/team-qualification-maps/new/',
            permanent=False,
        ),
    ),
    path(
        'setup/hr/teams/qualification-maps/<int:pk>/edit/',
        RedirectView.as_view(
            url='/setup/hr/team-qualification-maps/%(pk)s/edit/',
            permanent=False,
        ),
    ),
    path(
        'setup/grades/',
        RedirectView.as_view(url='/setup/hr/grades/', permanent=False),
    ),
    path(
        'setup/qualifications/',
        RedirectView.as_view(url='/setup/hr/qualifications/', permanent=False),
    ),
    path(
        'accounts/login/',
        LoginView.as_view(redirect_authenticated_user=True),
        name='login',
    ),
    path('accounts/logout/', LogoutView.as_view(), name='logout'),
]
