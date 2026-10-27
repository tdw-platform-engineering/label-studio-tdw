# TDW fork: add a Postgres-backed role to OrganizationMember.
# Source of truth is Cognito groups; synced on OIDC login, editable via
# /tdw/roles/. See README.tdw.md / PATCHES.md.

from django.db import migrations, models

from core.tdw_roles import ROLE_CHOICES, DEFAULT_ROLE


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0006_alter_organizationmember_deleted_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='organizationmember',
            name='role',
            field=models.CharField(
                choices=ROLE_CHOICES,
                default=DEFAULT_ROLE,
                help_text='TDW role (owner/manager/reviewer/annotator), synced from Cognito groups.',
                max_length=32,
                verbose_name='tdw role',
            ),
        ),
    ]
