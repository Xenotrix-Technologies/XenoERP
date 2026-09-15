from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0060_remove_contentitem_client_month_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='quotation',
            name='project_title',
            field=models.CharField(blank=True, default='Project Proposal', max_length=255),
        ),
        migrations.AddField(
            model_name='quotation',
            name='alt_phone',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='quotation',
            name='city',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='quotation',
            name='state',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='quotation',
            name='country',
            field=models.CharField(blank=True, default='India', max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='quotation',
            name='objective_text',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='quotation',
            name='deliverables_summary_text',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='quotation',
            name='success_metrics_text',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='quotation',
            name='declaration_text',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='quotation',
            name='sections_data_json',
            field=models.TextField(default='[]'),
        ),
        migrations.AddField(
            model_name='quotation',
            name='discount_type',
            field=models.CharField(default='fixed', max_length=20),
        ),
        migrations.AddField(
            model_name='quotation',
            name='discount_rate',
            field=models.DecimalField(decimal_places=2, default=0.0, max_digits=5),
        ),
        migrations.AddField(
            model_name='quotation',
            name='tax_rate',
            field=models.DecimalField(decimal_places=2, default=0.0, max_digits=5),
        ),
        migrations.AddField(
            model_name='quotationitem',
            name='deliverables',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='quotationitem',
            name='features',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='quotationitem',
            name='notes',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='quotationitem',
            name='discount_type',
            field=models.CharField(default='fixed', max_length=20),
        ),
        migrations.CreateModel(
            name='QuotationSection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('section_type', models.CharField(choices=[('objective', 'Project Objective'), ('deliverables', 'Deliverables Summary'), ('pricing_table', 'Pricing & Services Table'), ('milestones', 'Development & Delivery Schedule'), ('terms', 'Commercial Terms & Conditions'), ('exclusions', 'Third-Party Charges & Exclusions'), ('success_metrics', 'What Success Looks Like'), ('declaration', 'Declaration & Acceptance'), ('important_notes', 'Important Notes'), ('custom_text', 'Custom Section')], default='custom_text', max_length=50)),
                ('title', models.CharField(max_length=255)),
                ('content', models.TextField(blank=True, null=True)),
                ('position', models.IntegerField(default=0)),
                ('is_visible', models.BooleanField(default=True)),
                ('quotation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sections', to='crm.quotation')),
            ],
            options={
                'db_table': 'quotation_sections',
                'ordering': ['position', 'id'],
            },
        ),
    ]
