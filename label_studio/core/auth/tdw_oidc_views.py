"""
TDW OIDC views (fork-only) — AWS Cognito SSO for Label Studio.

Why self-contained
------------------
Label Studio 1.23.x resolves the browser page-view user through Django's session
auth. The stock `mozilla_django_oidc` callback reassigns `request.session`
mid-request (to reload from a store) and logs in with the OIDC backend; combined
with LS's middleware + session engine this lost the auth keys from the session
that actually gets persisted, so every SSO login bounced back to /user/login/.

So the callback here does the OAuth2 Authorization-Code exchange itself and then
performs ONE clean `django.contrib.auth.login(..., backend=ModelBackend)` on the
live `request.session` — exactly like LS's native `users.views.user_login`. No
session-object juggling. The authenticate view still stores state/nonce in the
session (reusing mozilla's request view).

Role mapping / user creation still happen in TDWCognitoOIDCBackend.authenticate,
which we call with the exchanged tokens.

TDW-owned module; only wired when settings.TDW_OIDC_ENABLED is true.
"""
import logging
import sys as _sys
def _d(m):
    print('TDWCB '+m, file=_sys.stderr, flush=True)

import requests
from django.conf import settings
from django.contrib import auth
from django.http import HttpResponseRedirect
from django.shortcuts import resolve_url
from django.urls import reverse
from mozilla_django_oidc.utils import absolutify
from mozilla_django_oidc.views import OIDCAuthenticationRequestView

logger = logging.getLogger(__name__)


class TDWOIDCAuthenticateView(OIDCAuthenticationRequestView):
    """Reuse mozilla's authorize-request view (stores state/nonce in session)."""


class TDWOIDCCallbackView(OIDCAuthenticationRequestView):
    """
    Self-contained Authorization-Code callback. We intentionally subclass the
    *request* view only to inherit get_settings(); the logic here is ours.
    """

    http_method_names = ['get']

    @staticmethod
    def _s(attr, default=None):
        from mozilla_django_oidc.utils import import_from_settings

        return import_from_settings(attr, default)

    def get(self, request):
        failure = resolve_url(self._s('LOGIN_REDIRECT_URL_FAILURE', '/user/login/'))
        success = resolve_url(self._s('LOGIN_REDIRECT_URL', '/'))

        code = request.GET.get('code')
        state = request.GET.get('state')
        _d('entry code=%s state=%s'%(bool(code),bool(state)))
        if not code or not state:
            logger.warning('TDW OIDC callback: missing code/state')
            return HttpResponseRedirect(failure)

        states = request.session.get('oidc_states') or {}
        if state not in states:
            _d('FAIL state-not-in-session states=%s'%list(states.keys()))
            logger.warning('TDW OIDC callback: state not in session')
            return HttpResponseRedirect(failure)
        nonce = states[state].get('nonce')
        code_verifier = states[state].get('code_verifier')
        # consume the state (replay protection)
        del states[state]
        request.session['oidc_states'] = states
        request.session.modified = True

        # Exchange the code for tokens directly.
        token_endpoint = self._s('OIDC_OP_TOKEN_ENDPOINT')
        client_id = self._s('OIDC_RP_CLIENT_ID')
        client_secret = self._s('OIDC_RP_CLIENT_SECRET')
        redirect_uri = absolutify(request, reverse('oidc_authentication_callback'))
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
        }
        if code_verifier:
            data['code_verifier'] = code_verifier
        try:
            resp = requests.post(
                token_endpoint,
                data=data,
                auth=(client_id, client_secret),
                timeout=self._s('OIDC_TIMEOUT', 15),
            )
            resp.raise_for_status()
            token_info = resp.json()
        except Exception as exc:
            _d('FAIL token-exchange %r'%exc)
            logger.error('TDW OIDC callback: token exchange failed: %s', exc)
            return HttpResponseRedirect(failure)

        # Authenticate via our backend (verifies id_token, maps role, creates user).
        user = auth.authenticate(
            request,
            nonce=nonce,
            code_verifier=code_verifier,
            # pass tokens so the backend doesn't re-exchange the (now consumed) code
            id_token=token_info.get('id_token'),
            access_token=token_info.get('access_token'),
            tdw_token_info=token_info,
        )
        if not user or not user.is_active:
            _d('FAIL authenticate-none')
            logger.warning('TDW OIDC callback: authenticate returned no active user')
            return HttpResponseRedirect(failure)

        # Set active org (LS pages require it) then ONE clean session login.
        try:
            from organizations.models import Organization

            org = Organization.find_by_user(user)
            if org is not None and user.active_organization_id != org.pk:
                user.active_organization_id = org.pk
                user.save(update_fields=['active_organization'])
        except Exception as exc:  # pragma: no cover
            logger.warning('TDW OIDC: set active_organization failed: %s', exc)

        auth.login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        request.session['keep_me_logged_in'] = True
        request.session.modified = True

        logger.info(
            'TDW OIDC login OK: user=%s role_org=%s auth_user_id=%s',
            user.email, getattr(user, 'active_organization_id', None),
            request.session.get('_auth_user_id'),
        )
        _d('SUCCESS auth_user_id=%s'%request.session.get('_auth_user_id'))
        return HttpResponseRedirect(success)
