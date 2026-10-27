"""
End-to-end / integration tests for the TDW Cognito OIDC + role patch.

Run inside the app environment (same as the container), e.g. in the pipeline's
build stage or locally:

    DJANGO_SETTINGS_MODULE=core.settings.label_studio DJANGO_DB=sqlite \
    SECRET_KEY=test TDW_OIDC_ENABLED=true \
    OIDC_OP_DOMAIN=example.auth.us-east-1.amazoncognito.com \
    OIDC_RP_CLIENT_ID=x OIDC_RP_CLIENT_SECRET=y \
    TDW_OIDC_GROUP_ROLE_MAP='{"ls-owners":"owner","ls-managers":"manager","ls-reviewers":"reviewer","ls-annotators":"annotator"}' \
    pytest label_studio/tests/test_tdw_oidc.py -v

These assert the behaviours TDW depends on: the backend maps OIDC claims ->
User + single org + role, cognito:groups -> role (highest-priv wins), owner ->
staff/superuser, re-login does not duplicate, and the seed command is correct.
"""
import pytest

pytestmark = pytest.mark.django_db


def _claims(email, groups=None, given="A", family="B"):
    c = {"email": email, "given_name": given, "family_name": family}
    if groups is not None:
        c["cognito:groups"] = groups
    return c


def _backend():
    from core.auth.tdw_oidc import TDWCognitoOIDCBackend

    return TDWCognitoOIDCBackend()


def test_role_from_groups_highest_privilege_wins():
    from core.auth.tdw_oidc import _role_from_groups

    assert _role_from_groups(["ls-annotators"]) == "annotator"
    assert _role_from_groups(["ls-owners", "ls-annotators"]) == "owner"
    assert _role_from_groups(["ls-managers", "ls-reviewers"]) == "manager"
    assert _role_from_groups([]) == "annotator"      # default
    assert _role_from_groups(["unknown"]) == "annotator"


def test_create_user_joins_single_org_with_role():
    from core.tdw_roles import role_for_user

    user = _backend().create_user(_claims("ann@tdw.group", ["ls-annotators"]))
    assert user.email == "ann@tdw.group"
    assert user.active_organization is not None
    assert role_for_user(user, user.active_organization) == "annotator"
    assert user.is_staff is False and user.is_superuser is False


def test_owner_group_grants_staff_superuser():
    from core.tdw_roles import role_for_user

    user = _backend().create_user(_claims("own@tdw.group", ["ls-owners"]))
    assert role_for_user(user, user.active_organization) == "owner"
    assert user.is_staff is True and user.is_superuser is True


def test_second_login_does_not_duplicate_and_resyncs_role():
    from organizations.models import OrganizationMember
    from core.tdw_roles import role_for_user

    b = _backend()
    user = b.create_user(_claims("x@tdw.group", ["ls-annotators"]))
    org = user.active_organization
    # promote via groups on the next login
    b.update_user(user, _claims("x@tdw.group", ["ls-managers"]))
    assert OrganizationMember.objects.filter(user=user, organization=org).count() == 1
    assert role_for_user(user, org) == "manager"


def test_all_oidc_users_share_the_single_org():
    from organizations.models import Organization

    b = _backend()
    b.create_user(_claims("u1@tdw.group", ["ls-annotators"]))
    b.create_user(_claims("u2@tdw.group", ["ls-managers"]))
    assert Organization.objects.count() == 1


def test_seed_command_creates_expected_roles():
    from django.core.management import call_command
    from organizations.models import OrganizationMember

    call_command("tdw_seed_users")
    roles = dict(OrganizationMember.objects.values_list("user__email", "role"))
    assert roles.get("wamaya@tdw.group") == "owner"
    assert roles.get("info@tdw.group") == "annotator"
