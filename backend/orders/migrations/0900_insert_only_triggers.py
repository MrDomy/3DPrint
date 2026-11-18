"""Защита order_event и audit_log от UPDATE/DELETE на уровне PostgreSQL (INSERT-ONLY).
Важно: после генерации миграций поправьте dependencies на последнюю миграцию приложения orders."""
from django.db import migrations

SQL = """
CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Таблица % доступна только для добавления (INSERT-ONLY)', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS order_event_insert_only ON order_event;
CREATE TRIGGER order_event_insert_only BEFORE UPDATE OR DELETE ON order_event
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
DROP TRIGGER IF EXISTS audit_log_insert_only ON audit_log;
CREATE TRIGGER audit_log_insert_only BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
"""
REVERSE = """
DROP TRIGGER IF EXISTS order_event_insert_only ON order_event;
DROP TRIGGER IF EXISTS audit_log_insert_only ON audit_log;
DROP FUNCTION IF EXISTS forbid_mutation();
"""


def forward(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(SQL)


def backward(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(REVERSE)


class Migration(migrations.Migration):
    dependencies = [('orders', '0001_initial')]
    operations = [migrations.RunPython(forward, backward)]
