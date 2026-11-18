from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('users', '0001_initial')]

    operations = [
        migrations.AddField('user', 'full_name', models.CharField(blank=True, default='', max_length=255)),
        migrations.AddField('user', 'client_type', models.CharField(
            choices=[('INDIVIDUAL', 'Физическое лицо'), ('COMPANY', 'Юридическое лицо')],
            default='INDIVIDUAL', max_length=16)),
        migrations.AddField('user', 'consent_at', models.DateTimeField(blank=True, null=True)),
        migrations.AddField('user', 'is_senior', models.BooleanField(default=False)),
        migrations.AddField('user', 'created_at', models.DateTimeField(auto_now_add=True, null=True)),
        migrations.AddField('user', 'updated_at', models.DateTimeField(auto_now=True, null=True)),
    ]
