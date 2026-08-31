"""Trial database provisioning and live→trial user copy."""

from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from psycopg import connect, sql


def live_database_name() -> str:
    return settings.LIVE_POSTGRES_DB


def trial_database_name() -> str:
    if settings.JK_ERP_IS_TRIAL:
        return settings.DATABASES['default']['NAME']
    return settings.TRIAL_POSTGRES_DB


def _postgres_connect(dbname: str):
    db = settings.DATABASES['default']
    timeout = db.get('OPTIONS', {}).get('connect_timeout', 10)
    return connect(
        dbname=dbname,
        user=db['USER'],
        password=db['PASSWORD'],
        host=db['HOST'],
        port=db['PORT'],
        connect_timeout=timeout,
    )


def database_exists(db_name: str) -> bool:
    with _postgres_connect('postgres') as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT 1 FROM pg_database WHERE datname = %s',
                (db_name,),
            )
            return cursor.fetchone() is not None


def trial_database_ready() -> tuple[bool, str | None]:
    db_name = trial_database_name()
    if not database_exists(db_name):
        return False, f'Database {db_name!r} does not exist yet.'
    try:
        connection.ensure_connection()
    except Exception as exc:
        return False, str(exc)
    return True, None


def create_trial_database() -> tuple[bool, str]:
    db_name = trial_database_name()
    if database_exists(db_name):
        return False, f'Database {db_name} already exists.'
    with _postgres_connect('postgres') as conn:
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL('CREATE DATABASE {}').format(sql.Identifier(db_name))
            )
    return True, f'Created database {db_name}.'


def provision_trial_database() -> str:
    """Create the trial database if needed, then run all migrations."""
    lines = []
    created, message = create_trial_database()
    lines.append(message)
    connection.close()
    connection.ensure_connection()
    out = StringIO()
    call_command('migrate', verbosity=2, stdout=out, stderr=out)
    lines.append(out.getvalue().strip())
    return '\n'.join(line for line in lines if line).strip()


def migration_status() -> dict:
    db_name = trial_database_name()
    ready, error = trial_database_ready()
    if not ready:
        return {
            'trial_db_ready': False,
            'trial_db_error': error,
            'database_name': db_name,
            'live_database_name': live_database_name(),
            'pending_migrations': [],
            'pending_count': 0,
        }

    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    plan = executor.migration_plan(targets)
    pending = [
        f'{migration.app_label}.{migration.name}'
        for migration, backwards in plan
        if not backwards
    ]
    return {
        'trial_db_ready': True,
        'trial_db_error': None,
        'database_name': db_name,
        'live_database_name': live_database_name(),
        'pending_migrations': pending,
        'pending_count': len(pending),
    }


def run_migrations() -> str:
    out = StringIO()
    call_command('migrate', verbosity=2, stdout=out, stderr=out)
    return out.getvalue().strip()


def trial_user_exists(username: str) -> bool:
    User = get_user_model()
    return User.objects.filter(username__iexact=username).exists()


def copy_user_from_live(username: str) -> str:
    username = username.strip()
    live_name = live_database_name()
    with _postgres_connect(live_name) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                '''
                SELECT username, password, email, is_superuser, is_staff,
                       is_active, first_name, last_name, last_login, date_joined
                FROM auth_user
                WHERE LOWER(username) = LOWER(%s)
                ''',
                (username,),
            )
            row = cursor.fetchone()
    if not row:
        raise ValueError(
            f'User {username!r} was not found in live database {live_name!r}.'
        )

    User = get_user_model()
    user, created = User.objects.update_or_create(
        username=row[0],
        defaults={
            'password': row[1],
            'email': row[2] or '',
            'is_superuser': row[3],
            'is_staff': row[4],
            'is_active': row[5],
            'first_name': row[6] or '',
            'last_name': row[7] or '',
            'last_login': row[8],
            'date_joined': row[9],
        },
    )
    verb = 'Created' if created else 'Updated'
    return (
        f'{verb} trial user {user.username!r} from live database '
        f'{live_name!r} (same password and admin flags).'
    )
