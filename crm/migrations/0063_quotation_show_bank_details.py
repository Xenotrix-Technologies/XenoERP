from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0062_documentsettings_branding'),
    ]

    operations = [
        migrations.AddField(
            model_name='quotation',
            name='show_bank_details',
            field=models.BooleanField(default=False),
        ),
    ]
