DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT 
            t.relname AS table_name,
            a.attname AS column_name,
            s.relname AS seq_name
        FROM pg_class s
        JOIN pg_depend d ON d.objid = s.oid AND d.classid = 'pg_class'::regclass
        JOIN pg_class t ON t.oid = d.refobjid AND d.refclassid = 'pg_class'::regclass
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
        WHERE s.relkind = 'S'
    ) LOOP
        EXECUTE format('SELECT setval(%L, COALESCE((SELECT MAX(%I) FROM %I), 1), (SELECT MAX(%I) IS NOT NULL FROM %I))', 
            r.seq_name, r.column_name, r.table_name, r.column_name, r.table_name);
    END LOOP;
END $$;

