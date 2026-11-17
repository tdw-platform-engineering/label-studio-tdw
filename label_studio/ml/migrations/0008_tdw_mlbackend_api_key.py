# TDW patch: API key authentication for ML backends.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ml', '0007_auto_20240314_1957'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mlbackend',
            name='auth_method',
            field=models.CharField(
                choices=[('NONE', 'None'), ('BASIC_AUTH', 'Basic Auth'), ('API_KEY', 'API Key')],
                default='NONE',
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name='mlbackend',
            name='api_key',
            field=models.TextField(
                blank=True,
                default='',
                help_text='API key sent to the ML backend (auth_method API_KEY)',
                null=True,
                verbose_name='api key',
            ),
        ),
        migrations.AddField(
            model_name='mlbackend',
            name='api_key_header',
            field=models.TextField(
                blank=True,
                default='Authorization',
                help_text='Header that carries the API key. With "Authorization" the value is sent as "Bearer <key>", with any other header (for example X-API-Key) the key is sent as is',
                null=True,
                verbose_name='api key header',
            ),
        ),
    ]
