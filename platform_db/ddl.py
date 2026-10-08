"""Non-table DDL the migration applies on top of ``create_all``: row-level
security (SRS 8.5) and the append-only audit-log trigger (SRS 8.4).

Kept here, as pure functions returning SQL strings, so the Alembic baseline stays
short and the policy wording is unit-testable without a database.
"""
from __future__ import annotations

# Session GUCs the API sets per request (SRS 8.5). `application_ids` is a
# comma-separated list of the UUIDs the caller may see; `bypass_rls` = 'on' lets a
# global role (Admin, DPO, Auditor) see everything. Both are LOCAL to the
# transaction, so a connection returned to the pool carries no leftover grant.
SESSION_VAR_APP_IDS = "privacymon.application_ids"
SESSION_VAR_BYPASS = "privacymon.bypass_rls"

# Tables whose rows are scoped to an application, with the column that carries the
# application id. `applications` itself is keyed on its own primary key.
RLS_TABLES: dict[str, str] = {
    "applications": "id",
    "data_sources": "application_id",
    "findings": "application_id",
    "inventory": "application_id",
    "dpia_assessments": "application_id",
    "questionnaire_responses": "application_id",
    "dpia_comments": "application_id",
    "risks": "application_id",
    "dpia_transitions": "application_id",
    "dpia_records": "application_id",
}


def _predicate(key: str) -> str:
    # NULL/empty GUC -> string_to_array returns NULL -> `= ANY(NULL)` is NULL (not
    # true) -> the row is hidden. So an unset context is fail-CLOSED unless bypass.
    return (
        f"current_setting('{SESSION_VAR_BYPASS}', true) = 'on' "
        f"OR {key} = ANY (string_to_array("
        f"nullif(current_setting('{SESSION_VAR_APP_IDS}', true), ''), ',')::uuid[])"
    )


def rls_up_table(table: str, key: str) -> list[str]:
    """Enable + FORCE RLS and install the application-isolation policy on one table.
    FORCE so the policy applies even to the table owner — the whole point of 8.5 is
    that a leak survives neither an API bug nor a privileged role."""
    pred = _predicate(key)
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY {table}_app_isolation ON {table}\n"
        f"    USING ({pred})\n"
        f"    WITH CHECK ({pred})",
    ]


def rls_down_table(table: str) -> list[str]:
    return [
        f"DROP POLICY IF EXISTS {table}_app_isolation ON {table}",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
    ]


def rls_up() -> list[str]:
    out: list[str] = []
    for table, key in RLS_TABLES.items():
        out.extend(rls_up_table(table, key))
    return out


def rls_down() -> list[str]:
    out: list[str] = []
    for table in RLS_TABLES:
        out.extend(rls_down_table(table))
    return out


def audit_trigger_up() -> list[str]:
    """Reject UPDATE and DELETE on ``audit_log`` so the log is append-only even to a
    role holding those privileges (SRS 8.4)."""
    return [
        "CREATE OR REPLACE FUNCTION privacymon_reject_mutation() RETURNS trigger AS $$\n"
        "BEGIN\n"
        "    RAISE EXCEPTION 'audit_log is append-only: % is not permitted', TG_OP;\n"
        "END;\n"
        "$$ LANGUAGE plpgsql",
        "CREATE TRIGGER audit_log_append_only\n"
        "    BEFORE UPDATE OR DELETE ON audit_log\n"
        "    FOR EACH ROW EXECUTE FUNCTION privacymon_reject_mutation()",
    ]


def audit_trigger_down() -> list[str]:
    return [
        "DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log",
        "DROP FUNCTION IF EXISTS privacymon_reject_mutation()",
    ]
