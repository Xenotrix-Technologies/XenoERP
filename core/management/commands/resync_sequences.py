from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Resynchronize PostgreSQL auto-increment sequences (SERIAL / IDENTITY) to match MAX(id) for all tables."

    def handle(self, *args, **options):
        self.stdout.write("Inspecting database sequences...")

        if connection.vendor != 'postgresql':
            self.stdout.write(self.style.WARNING(f"Database backend is '{connection.vendor}'. Sequence resync is only required for PostgreSQL."))
            return

        query = """
        SELECT 
            t.relname AS table_name,
            a.attname AS column_name,
            s.relname AS seq_name
        FROM pg_class s
        JOIN pg_depend d ON d.objid = s.oid AND d.classid = 'pg_class'::regclass
        JOIN pg_class t ON t.oid = d.refobjid AND d.refclassid = 'pg_class'::regclass
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
        WHERE s.relkind = 'S'
        ORDER BY t.relname;
        """

        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            
            resynced = 0
            for table_name, column_name, seq_name in rows:
                cursor.execute(f'SELECT COALESCE(MAX("{column_name}"), 0) FROM "{table_name}";')
                max_id = cursor.fetchone()[0]

                if max_id > 0:
                    cursor.execute(f'SELECT setval(\'"{seq_name}"\', {max_id}, true);')
                    self.stdout.write(f"  - {table_name}.{column_name}: set sequence '{seq_name}' to {max_id} (next value: {max_id + 1})")
                else:
                    cursor.execute(f'SELECT setval(\'"{seq_name}"\', 1, false);')
                    self.stdout.write(f"  - {table_name}.{column_name}: set sequence '{seq_name}' to 1 (empty table)")
                resynced += 1

        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully synchronized {resynced} PostgreSQL sequences!"))

