p = 'config/views/utilities.py'
s = open(p, encoding='utf-8').read()
marker = 'from .utility_jobs import *  # noqa: F403'
block = marker + '''
from .utility_jobs import (
    _DUPLICATE_JOBS,
    _DUPLICATE_JOBS_LOCK,
    _SIMILAR_JOBS,
    _SIMILAR_JOBS_LOCK,
    _SIMILAR_REF_JOBS,
    _SIMILAR_REF_JOBS_LOCK,
    _EXCEL_IMPORT_JOBS,
    _EXCEL_IMPORT_JOBS_LOCK,
    _MOVE_ALL_JOBS,
    _MOVE_ALL_JOBS_LOCK,
    _RENAME_SOA_JOBS,
    _RENAME_SOA_JOBS_LOCK,
    _start_duplicate_job,
    _start_similar_files_job,
    _start_similar_to_reference_job,
    _start_excel_import_job,
    _start_move_all_files_job,
    _start_rename_soa_job,
    _save_excel_import_preferences,
    _is_truthy_form_value,
    _excel_import_mapping_warning,
)'''
count = s.count(marker)
print('marker found:', count, 'times')
if count == 1:
    s = s.replace(marker, block, 1)
    open(p, 'w', encoding='utf-8').write(s)
    print('DONE - file updated')
else:
    print('ABORTED - marker not found exactly once')
    