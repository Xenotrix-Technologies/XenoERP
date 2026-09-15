from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0061_quotation_updates'),
    ]

    operations = [
        migrations.AddField(
            model_name='documentsettings',
            name='logo_choice',
            field=models.CharField(choices=[('asset', 'Default Xenotrix Logo (static/images/xenotrix.png)'), ('upload', 'Uploaded Logo File'), ('url', 'Custom Logo URL')], default='asset', max_length=20),
        ),
        migrations.AddField(
            model_name='documentsettings',
            name='logo_file',
            field=models.FileField(blank=True, null=True, upload_to='branding/'),
        ),
        migrations.AddField(
            model_name='documentsettings',
            name='seal_choice',
            field=models.CharField(choices=[('asset', 'Default Company Seal (static/images/seal.png)'), ('upload', 'Uploaded Seal File'), ('url', 'Custom Seal URL'), ('none', 'No Seal')], default='asset', max_length=20),
        ),
        migrations.AddField(
            model_name='documentsettings',
            name='seal_url',
            field=models.URLField(blank=True, max_length=1000, null=True),
        ),
        migrations.AddField(
            model_name='documentsettings',
            name='seal_file',
            field=models.FileField(blank=True, null=True, upload_to='branding/'),
        ),
        migrations.AddField(
            model_name='documentsettings',
            name='signature_file',
            field=models.FileField(blank=True, null=True, upload_to='branding/'),
        ),
    ]
