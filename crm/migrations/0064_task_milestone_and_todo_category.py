from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0063_quotation_show_bank_details'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE task_milestones ADD COLUMN IF NOT EXISTS category character varying(50) DEFAULT 'milestone_deliverable';
                ALTER TABLE task_todos ADD COLUMN IF NOT EXISTS category character varying(50) DEFAULT 'milestone_deliverable';
            """,
            reverse_sql="""
                ALTER TABLE task_milestones DROP COLUMN IF EXISTS category;
                ALTER TABLE task_todos DROP COLUMN IF EXISTS category;
            """
        ),
    ]
