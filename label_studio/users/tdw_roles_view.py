"""
/tdw/roles/ — a minimal admin page to set an organization member's role.

Access: owner + manager only. Cognito is the SOURCE OF TRUTH, so saving a role:
  1. writes the Cognito groups (AdminAddUserToGroup / AdminRemoveUserFromGroup)
     via boto3 using the EC2 instance role (no static keys), then
  2. updates the local OrganizationMember.role so the UI reflects it immediately
     (the next OIDC login re-syncs from Cognito and will already match).

TDW-owned module (conflict-free on upstream rebase). Only mounted when
settings.TDW_OIDC_ENABLED is true (see core/urls.py).
"""
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render

from core.tdw_roles import (
    MANAGEMENT_ROLES,
    ROLE_CHOICES,
    is_management,
    normalize_role,
    role_for_user,
    set_role,
)

logger = logging.getLogger(__name__)


def _invert_group_role_map():
    """role -> cognito group name, from settings.TDW_OIDC_GROUP_ROLE_MAP."""
    inv = {}
    for group, role in (getattr(settings, 'TDW_OIDC_GROUP_ROLE_MAP', {}) or {}).items():
        inv.setdefault(normalize_role(role), group)
    return inv


def _cognito_set_group(email, new_role):
    """
    Make the user's Cognito groups reflect exactly `new_role`: add the mapped
    group, remove the others. Returns (ok, message).
    """
    import boto3

    pool_id = getattr(settings, 'TDW_COGNITO_USER_POOL_ID', '')
    region = getattr(settings, 'TDW_COGNITO_REGION', 'us-east-1')
    role_to_group = _invert_group_role_map()
    target_group = role_to_group.get(new_role)

    if not pool_id:
        return False, 'TDW_COGNITO_USER_POOL_ID not configured'
    if not target_group:
        return False, f'No Cognito group mapped to role "{new_role}"'

    client = boto3.client('cognito-idp', region_name=region)
    username = email  # email is the sign-in alias in our pool
    try:
        client.admin_add_user_to_group(UserPoolId=pool_id, Username=username, GroupName=target_group)
        for role, group in role_to_group.items():
            if group != target_group:
                try:
                    client.admin_remove_user_from_group(UserPoolId=pool_id, Username=username, GroupName=group)
                except Exception:
                    pass
        return True, f'Cognito group set to {target_group}'
    except Exception as e:  # noqa
        logger.exception('TDW roles: Cognito update failed for %s', email)
        return False, f'Cognito update failed: {e}'


@login_required
def tdw_roles_view(request):
    org = request.user.active_organization
    if org is None or not is_management(request.user, org):
        return HttpResponseForbidden('You must be an owner or manager to manage roles.')

    from organizations.models import OrganizationMember

    message = error = None

    if request.method == 'POST':
        member_id = request.POST.get('member_id')
        new_role = normalize_role(request.POST.get('role'))
        om = (
            OrganizationMember.objects.filter(id=member_id, organization=org, deleted_at__isnull=True)
            .select_related('user')
            .first()
        )
        if not om:
            request.session['tdw_roles_error'] = 'Member not found.'
        else:
            acting_role = role_for_user(request.user, org)
            if new_role == 'owner' and acting_role != 'owner':
                request.session['tdw_roles_error'] = 'Only an owner can grant the owner role.'
            else:
                ok, msg = _cognito_set_group(om.user.email, new_role)
                set_role(om.user, org, new_role)
                if ok:
                    request.session['tdw_roles_message'] = f'{om.user.email}: role set to {new_role}. {msg}'
                else:
                    request.session['tdw_roles_error'] = (
                        f'Local role updated to {new_role}, but Cognito write failed: {msg}'
                    )
        return redirect('tdw-roles')

    members = (
        OrganizationMember.objects.filter(organization=org, deleted_at__isnull=True)
        .select_related('user')
        .order_by('user__email')
    )
    context = {
        'members': members,
        'role_choices': ROLE_CHOICES,
        'my_role': role_for_user(request.user, org),
        'management_roles': sorted(MANAGEMENT_ROLES),
        'message': request.session.pop('tdw_roles_message', None),
        'error': request.session.pop('tdw_roles_error', None),
        'cognito_pool': getattr(settings, 'TDW_COGNITO_USER_POOL_ID', ''),
    }
    return render(request, 'tdw/roles.html', context)
