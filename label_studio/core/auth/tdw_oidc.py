"""
TDWCognitoOIDCBackend — AWS Cognito OIDC authentication backend for the
`label-studio-tdw` fork (base: upstream 1.23.2, Django 5.2, Python 3.13).

On OIDC login:
  1. Resolve the OIDC `email` claim to a Label Studio `users.User` (create on
     first login).
  2. Attach the user to the SINGLE organization (community = single-org),
     mirroring the normal signup org-join.
  3. Map `cognito:groups` -> TDW role (owner/manager/reviewer/annotator) via the
     configurable settings.TDW_OIDC_GROUP_ROLE_MAP, persist on
     OrganizationMember.role, and set is_staff/is_superuser for an `owner`.

Cognito is the SOURCE OF TRUTH for roles: read on every login, local role
re-synced to match. /tdw/roles/ edits Cognito so the two never diverge.

TDW-owned module (upstream never edits it). Only active when
settings.TDW_OIDC_ENABLED is true.
"""
import logging

from django.conf import settings
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from core.tdw_roles import DEFAULT_ROLE, ROLE_OWNER, ROLE_RANK, normalize_role

logger = logging.getLogger(__name__)


def _role_from_groups(groups):
    """Highest-privilege TDW role for the given Cognito groups (else DEFAULT_ROLE)."""
    group_map = getattr(settings, 'TDW_OIDC_GROUP_ROLE_MAP', {}) or {}
    best, best_rank = None, -1
    for g in groups or []:
        mapped = group_map.get(g)
        if not mapped:
            continue
        mapped = normalize_role(mapped)
        if ROLE_RANK.get(mapped, -1) > best_rank:
            best, best_rank = mapped, ROLE_RANK[mapped]
    return best or DEFAULT_ROLE


def _extract_groups(claims):
    groups = claims.get('cognito:groups') or claims.get('groups') or []
    if isinstance(groups, str):
        groups = [groups]
    return list(groups)


class TDWCognitoOIDCBackend(OIDCAuthenticationBackend):
    def filter_users_by_claims(self, claims):
        email = (claims.get('email') or '').lower()
        if not email:
            return self.UserModel.objects.none()
        return self.UserModel.objects.filter(email__iexact=email)

    def create_user(self, claims):
        email = (claims.get('email') or '').lower()
        user = self.UserModel.objects.create_user(email=email)
        user.username = email.split('@')[0]
        user.first_name = claims.get('given_name', '') or claims.get('name', '')
        user.last_name = claims.get('family_name', '')
        user.set_unusable_password()  # SSO-only account
        user.save()
        self._attach_org_and_role(user, claims)
        logger.info('TDW OIDC: created user %s', email)
        return user

    def update_user(self, user, claims):
        changed = []
        gn = claims.get('given_name', '') or claims.get('name', '')
        fn = claims.get('family_name', '')
        if gn and user.first_name != gn:
            user.first_name = gn
            changed.append('first_name')
        if fn and user.last_name != fn:
            user.last_name = fn
            changed.append('last_name')
        if changed:
            user.save(update_fields=changed)
        self._attach_org_and_role(user, claims)
        return user

    # ------------------------------------------------------------------ #
    def _attach_org_and_role(self, user, claims):
        from organizations.models import Organization
        from core.tdw_roles import set_role

        if Organization.objects.exists():
            org = Organization.objects.first()
            org.add_user(user)
        else:
            title = getattr(settings, 'TDW_OIDC_DEFAULT_ORG_TITLE', 'TDW')
            org = Organization.create_organization(created_by=user, title=title)

        if user.active_organization_id != org.id:
            user.active_organization = org
            user.save(update_fields=['active_organization'])

        role = _role_from_groups(_extract_groups(claims))
        set_role(user, org, role)

        is_owner = role == ROLE_OWNER
        flags = []
        if user.is_staff != is_owner:
            user.is_staff = is_owner
            flags.append('is_staff')
        if user.is_superuser != is_owner:
            user.is_superuser = is_owner
            flags.append('is_superuser')
        if flags:
            user.save(update_fields=flags)
