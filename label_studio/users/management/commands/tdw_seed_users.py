"""
TDW management command: seed the initial Label Studio users + roles.

  wamaya@tdw.group  -> owner
  info@tdw.group    -> annotator

Idempotent: safe to run repeatedly (used at container startup). These users are
SSO-only (unusable local password); they log in via Cognito. Roles are also set
in Cognito by Terraform (the pool's seed groups/users), so this command just
ensures the LOCAL Label Studio side exists and matches on a fresh database.

Usage:
    python label_studio/manage.py tdw_seed_users
    TDW_SEED_USERS='{"a@x.com":"owner","b@x.com":"annotator"}' ... tdw_seed_users
"""
import json
import os

from django.core.management.base import BaseCommand

from core.tdw_roles import normalize_role, set_role

DEFAULT_SEED = {
    'wamaya@tdw.group': 'owner',
    'info@tdw.group': 'annotator',
}


class Command(BaseCommand):
    help = 'Seed TDW initial users and their org roles (idempotent).'

    def handle(self, *args, **options):
        from organizations.models import Organization
        from users.models import User

        seed = DEFAULT_SEED
        env_seed = os.environ.get('TDW_SEED_USERS')
        if env_seed:
            try:
                seed = json.loads(env_seed)
            except Exception:
                self.stderr.write('TDW_SEED_USERS is not valid JSON; using defaults.')

        org = Organization.objects.first()

        for email, role in seed.items():
            email = email.lower()
            role = normalize_role(role)
            user = User.objects.filter(email__iexact=email).first()
            created = False
            if user is None:
                user = User.objects.create_user(email=email)
                user.username = email.split('@')[0]
                user.set_unusable_password()
                user.save()
                created = True

            if org is None:
                org = Organization.create_organization(
                    created_by=user, title=os.environ.get('TDW_OIDC_DEFAULT_ORG_TITLE', 'TDW')
                )
            else:
                org.add_user(user)

            if user.active_organization_id != org.id:
                user.active_organization = org
                user.save(update_fields=['active_organization'])

            set_role(user, org, role)

            is_owner = role == 'owner'
            if user.is_staff != is_owner or user.is_superuser != is_owner:
                user.is_staff = is_owner
                user.is_superuser = is_owner
                user.save(update_fields=['is_staff', 'is_superuser'])

            self.stdout.write(self.style.SUCCESS(f"{'created' if created else 'updated'} {email} -> {role}"))

        self.stdout.write(self.style.SUCCESS('TDW seed complete.'))
