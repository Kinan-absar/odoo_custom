"""Replace global device-token uniqueness without deleting device records."""
from psycopg2 import sql


def migrate(cr, version):
    # Odoo can shorten/hash long constraint identifiers. Find the old global
    # unique constraint by its actual columns rather than guessing its name.
    cr.execute("""
        SELECT c.conname
          FROM pg_constraint c
          JOIN pg_attribute a
            ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
         WHERE c.conrelid = to_regclass('employee_portal_attendance_device')
           AND c.contype = 'u'
         GROUP BY c.oid, c.conname
        HAVING array_agg(a.attname::text ORDER BY a.attname::text) = ARRAY['token_hash']::text[]
    """)
    for (name,) in cr.fetchall():
        cr.execute(sql.SQL('ALTER TABLE {} DROP CONSTRAINT {}').format(
            sql.Identifier('employee_portal_attendance_device'), sql.Identifier(name),
        ))
    # The model's employee_token_uniq is installed by normal registry schema init.
