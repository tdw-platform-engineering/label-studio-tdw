"""TDW security patch: no native sign-up when SSO is on (incident 2026-11-25)."""
import pytest
from django.test import override_settings
from organizations.models import Organization
from users.models import User


@pytest.mark.django_db
@override_settings(TDW_DISABLE_NATIVE_SIGNUP=True, DISABLE_SIGNUP_WITHOUT_LINK=True)
def test_signup_page_and_post_are_gone(client):
    assert client.get('/user/signup/').status_code == 404
    before = User.objects.count()
    r = client.post('/user/signup/', {'email': 'evil@example.org', 'password': 'Passw0rd!x', 'allow_newsletters': False})
    assert r.status_code == 404
    assert User.objects.count() == before


@pytest.mark.django_db
@override_settings(TDW_DISABLE_NATIVE_SIGNUP=True, DISABLE_SIGNUP_WITHOUT_LINK=True)
def test_signup_with_invite_token_is_gone(client, business_client):
    token = Organization.objects.first().token
    r = client.post(f'/user/signup/?token={token}', {'email': 'evil2@example.org', 'password': 'Passw0rd!x'})
    assert r.status_code == 404
    assert not User.objects.filter(email='evil2@example.org').exists()


@pytest.mark.django_db
@override_settings(TDW_DISABLE_NATIVE_SIGNUP=True)
def test_api_user_create_is_forbidden(business_client):
    r = business_client.post('/api/users/', {'email': 'evil3@example.org', 'username': 'evil3'})
    assert r.status_code == 403
    assert not User.objects.filter(email='evil3@example.org').exists()


@pytest.mark.django_db
@override_settings(TDW_DISABLE_NATIVE_SIGNUP=False, DISABLE_SIGNUP_WITHOUT_LINK=False)
def test_upstream_behaviour_when_flag_off(client):
    assert client.get('/user/signup/').status_code == 200
