"""PostgreSQL row-level security (RLS) for department-owned records.

The application already scopes querysets in Python, but a single missed
``filter()`` must not be able to leak another department's row. These policies
are the database-level backstop.

Design
------
* Django connections start with ``app.bypass_rls = 'on'`` (via the
  ``OPTIONS`` connection setting) so migrations, management commands and
  tests can create/read data across departments.
* :class:`core.middleware.RLSMiddleware` sets ``app.bypass_rls = 'off'`` for
  every authenticated non-superuser request, together with
  ``app.department_id`` and ``app.user_id``. The values are reset afterwards.
* A row is visible when it belongs to the current department, is explicitly
  shared (controls), is granted through django-guardian, or is a notification
  addressed to the current user.
* Per-user MFA rows (TOTP secret and hashed backup codes) are visible only to
  their owner; superusers retain the bypass.
* ``core_user`` is deliberately excluded: authentication and identity lookups
  must remain available before a department context exists.
* Org-wide ``RiskAppetite`` rows (``department_id IS NULL``) stay visible.

The policies are installed by migration ``core.0011_enable_rls`` and can be
re-applied with ``python manage.py enable_rls``. They require PostgreSQL; the
middleware is a no-op on other backends.
"""
from django.contrib.auth import get_user_model
from django.db import connection as default_connection

from .permissions import SHAREABLE_MODELS

# Tables that must never be filtered by department RLS.
EXCLUDED_TABLES = {
    'core_user',
    'core_historicaluser',
    'policies_policy_applies_to_departments',
}

# Keep this in step with core.permissions.SHAREABLE_MODELS: an object grant
# that the Python scoping layer honours must also be honoured by RLS.
SHAREABLE_LABELS = set(SHAREABLE_MODELS)

POLICY_NAME = 'grc_dept_isolation'


def _model_label(table_name):
    """Map a table (including a simple-history table) to ``app.model``."""
    base = table_name.replace('_historical', '_')
    if '_' not in base:
        return base
    app_label, model = base.split('_', 1)
    return f'{app_label}.{model}'


def _columns(cursor):
    cursor.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND column_name IN (
              'owner_dept_id', 'department_id', 'recipient_id', 'is_shared',
              'user_id'
          )
        """
    )
    columns = {}
    for table, column in cursor.fetchall():
        columns.setdefault(table, set()).add(column)
    return columns


def _base_tables(cursor):
    cursor.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """
    )
    return {row[0] for row in cursor.fetchall()}


def _expression(table, columns):
    label = _model_label(table)
    bypass = "current_setting('app.bypass_rls', true) = 'on'"
    dept = "nullif(current_setting('app.department_id', true), '')::bigint"
    user = "nullif(current_setting('app.user_id', true), '')::bigint"

    # TOTP secrets and hashed backup codes are per-user data and must never be
    # visible to another ordinary account, even through a missed ORM filter.
    if table == 'core_usermfa' and 'user_id' in columns:
        return f'{bypass} OR user_id = {user}'

    if 'owner_dept_id' in columns:
        parts = [bypass, f'owner_dept_id = {dept}']
        if 'is_shared' in columns:
            parts.append('is_shared = true')
        if 'recipient_id' in columns:
            parts.append(f'recipient_id = {user}')
        if label in SHAREABLE_LABELS:
            parts.append(f"grc_can_access('{label}', id)")
        if table == 'policies_policy':
            # A policy is readable by the departments it applies to, and a
            # policy with no audience rows is organisation-wide. This mirrors
            # PolicyDetailView without granting write access.
            parts.append(
                'NOT EXISTS ('
                'SELECT 1 FROM policies_policy_applies_to_departments p '
                'WHERE p.policy_id = policies_policy.id)'
            )
            parts.append(
                'EXISTS ('
                'SELECT 1 FROM policies_policy_applies_to_departments p '
                'WHERE p.policy_id = policies_policy.id '
                f'AND p.department_id = {dept})'
            )
        return ' OR '.join(parts)

    if 'department_id' in columns:
        parts = [bypass, f'department_id = {dept}']
        # Risk appetite rows with a NULL department are organisation-wide.
        if label == 'risks.riskappetite':
            parts.append('department_id IS NULL')
        return ' OR '.join(parts)

    return None


def build_statements(connection=None):
    """Return the SQL statements needed to install the policies."""
    connection = connection or default_connection
    statements = []
    with connection.cursor() as cursor:
        columns = _columns(cursor)
        tables = _base_tables(cursor)

    # The project uses a custom user model, so the groups M2M table is
    # ``core_user_groups`` rather than ``auth_user_groups``. Derive it instead
    # of hard-coding so a future user-model move does not silently break RLS.
    groups_table = (
        get_user_model()._meta.get_field('groups').remote_field.through._meta.db_table
    )
    statements.append(
        f"""
        CREATE OR REPLACE FUNCTION grc_can_access(p_table text, p_pk bigint)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM guardian_userobjectpermission uop
                JOIN django_content_type ct ON ct.id = uop.content_type_id
                WHERE uop.user_id =
                      nullif(current_setting('app.user_id', true), '')::bigint
                  AND ct.app_label || '.' || ct.model = p_table
                  AND uop.object_pk = p_pk::text
            ) OR EXISTS (
                SELECT 1
                FROM guardian_groupobjectpermission gop
                JOIN django_content_type ct ON ct.id = gop.content_type_id
                JOIN "{groups_table}" ug ON ug.group_id = gop.group_id
                WHERE ug.user_id =
                      nullif(current_setting('app.user_id', true), '')::bigint
                  AND ct.app_label || '.' || ct.model = p_table
                  AND gop.object_pk = p_pk::text
            );
        $$
        """
    )

    for table in sorted(tables):
        if table in EXCLUDED_TABLES:
            continue
        table_columns = columns.get(table, set())
        expression = _expression(table, table_columns)
        if not expression:
            continue
        statements.extend([
            f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY',
            f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY',
            f'DROP POLICY IF EXISTS {POLICY_NAME} ON "{table}"',
            (
                f'CREATE POLICY {POLICY_NAME} ON "{table}" FOR ALL '
                f'USING ({expression}) WITH CHECK ({expression})'
            ),
        ])
    return statements


def apply_rls(apps=None, schema_editor=None, connection=None, dry_run=False):
    """Install (or re-install) RLS policies. Safe to run repeatedly."""
    connection = connection or (
        schema_editor.connection if schema_editor is not None else default_connection
    )
    if connection.vendor != 'postgresql':
        return []
    statements = build_statements(connection)
    if dry_run:
        return statements
    with connection.cursor() as cursor:
        # The migration/command itself must be able to read every row while it
        # installs policies.
        cursor.execute("SELECT set_config('app.bypass_rls', 'on', false)")
        # A fresh database may create the guardian tables after core.0011;
        # defer validation of the helper function's body until it is called.
        cursor.execute('SET check_function_bodies = false')
        for statement in statements:
            cursor.execute(statement)
        cursor.execute('SET check_function_bodies = true')
    return statements


def remove_rls(apps=None, schema_editor=None, connection=None):
    """Disable the policies (used by the migration reverse operation)."""
    connection = connection or (
        schema_editor.connection if schema_editor is not None else default_connection
    )
    if connection.vendor != 'postgresql':
        return
    with connection.cursor() as cursor:
        columns = _columns(cursor)
        tables = _base_tables(cursor)
        for table in sorted(tables):
            if table in EXCLUDED_TABLES or not _expression(table, columns.get(table, set())):
                continue
            cursor.execute(f'DROP POLICY IF EXISTS {POLICY_NAME} ON "{table}"')
            cursor.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
        cursor.execute('DROP FUNCTION IF EXISTS grc_can_access(text, bigint)')
