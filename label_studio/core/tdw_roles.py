"""
TDW role model for Label Studio (fork `label-studio-tdw`).

Adds a simple, Postgres-backed role to `OrganizationMember` so Cognito groups can
map to a meaningful role inside Label Studio. Community Label Studio has no native
per-member role (only the derived `is_owner`), so this module supplies the role
vocabulary + the permission helpers our patches enforce.

Source of truth for *who has which role* is **AWS Cognito groups** — the role here
is a local cache, (re)synced on every OIDC login and editable via the `/tdw/roles/`
mini admin page (which writes back to Cognito). See README.tdw.md.

This module is TDW-owned (upstream never touches it) so it is conflict-free on
upstream rebases.
"""

# Role vocabulary (ordered least -> most privileged).
ROLE_ANNOTATOR = 'annotator'
ROLE_REVIEWER = 'reviewer'
ROLE_MANAGER = 'manager'
ROLE_OWNER = 'owner'

ROLE_CHOICES = [
    (ROLE_ANNOTATOR, 'Annotator'),
    (ROLE_REVIEWER, 'Reviewer'),
    (ROLE_MANAGER, 'Manager'),
    (ROLE_OWNER, 'Owner'),
]

DEFAULT_ROLE = ROLE_ANNOTATOR

# Privilege ordering for comparisons (higher = more privileged).
ROLE_RANK = {
    ROLE_ANNOTATOR: 0,
    ROLE_REVIEWER: 1,
    ROLE_MANAGER: 2,
    ROLE_OWNER: 3,
}

# Roles allowed to manage people + project settings and open /tdw/roles/.
MANAGEMENT_ROLES = {ROLE_MANAGER, ROLE_OWNER}


def normalize_role(value):
    """Coerce an arbitrary string to a known role, falling back to DEFAULT_ROLE."""
    if not value:
        return DEFAULT_ROLE
    value = str(value).strip().lower()
    return value if value in ROLE_RANK else DEFAULT_ROLE


def role_for_user(user, organization=None):
    """
    Return the TDW role string for a user in an organization.

    Resolves the OrganizationMember.role column. Falls back to the user's
    active_organization when no organization is given, and to DEFAULT_ROLE when
    no membership/role is found.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return DEFAULT_ROLE
    org = organization or getattr(user, 'active_organization', None)
    if org is None:
        return DEFAULT_ROLE
    try:
        from organizations.models import OrganizationMember

        om = OrganizationMember.objects.filter(
            user=user, organization=org, deleted_at__isnull=True
        ).first()
        if om and getattr(om, 'role', None):
            return normalize_role(om.role)
    except Exception:
        # Never let role resolution break a request; degrade to the default.
        pass
    return DEFAULT_ROLE


def is_management(user, organization=None):
    """True if the user is a manager or owner in the organization."""
    return role_for_user(user, organization) in MANAGEMENT_ROLES


def set_role(user, organization, role):
    """
    Set (and persist) the local OrganizationMember.role for a user. Does NOT
    touch Cognito — callers that want Cognito as the source of truth must update
    the Cognito group separately (see users.tdw_roles_view).
    """
    from organizations.models import OrganizationMember

    role = normalize_role(role)
    om = OrganizationMember.objects.filter(
        user=user, organization=organization, deleted_at__isnull=True
    ).first()
    if om is None:
        return None
    if om.role != role:
        om.role = role
        om.save(update_fields=['role'])
    return om
