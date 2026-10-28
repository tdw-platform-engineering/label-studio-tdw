"""
TDW OIDC callback view (fork-only).

Why this exists
---------------
Label Studio 1.23.x resolves the request user for browser page views through
Django's standard session auth (SessionMiddleware + AuthenticationMiddleware);
its native login (`users.views.user_login`) calls
`login(request, user, backend='django.contrib.auth.backends.ModelBackend')` and
ALSO sets `user.active_organization_id`. The bare
`mozilla_django_oidc` callback logs the user in with the OIDC backend path and
does NOT set `active_organization`, which left the post-login redirect bouncing
back to `/user/login/` (session present but the app treated the user as not
fully logged in).

This subclass keeps all of mozilla's code-exchange / token-verify / role-mapping
(via TDWCognitoOIDCBackend) and only customizes `login_success()` so the session
is established EXACTLY like LS's native login:
  * active_organization is set (LS pages expect it),
  * the session is persisted,
  * verbose logging so failures are diagnosable in CloudWatch.

TDW-owned module; only reachable when settings.TDW_OIDC_ENABLED is true.
"""
import logging

from django.conf import settings
from mozilla_django_oidc.views import (
    OIDCAuthenticationCallbackView,
    OIDCAuthenticationRequestView,
)

logger = logging.getLogger(__name__)


class TDWOIDCAuthenticateView(OIDCAuthenticationRequestView):
    def get(self, request):
        response = super().get(request)
        try:
            logger.info(
                'TDW OIDC authenticate: session_key=%s oidc_states=%s',
                request.session.session_key,
                list((request.session.get('oidc_states') or {}).keys()),
            )
        except Exception as exc:  # pragma: no cover
            logger.warning('TDW OIDC authenticate log failed: %s', exc)
        return response


class TDWOIDCCallbackView(OIDCAuthenticationCallbackView):
    def dispatch(self, request, *args, **kwargs):
        import sys as _sys
        print('TDWDIAG callback dispatch hit path=%s GET=%s' % (request.path, dict(request.GET)), file=_sys.stderr, flush=True)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        import sys as _sys
        try:
            print('TDWDIAG callback get: session_key=%s has_oidc_states=%s states=%s cookie=%s' % (
                request.session.session_key,
                'oidc_states' in request.session,
                list((request.session.get('oidc_states') or {}).keys()),
                'sessionid' in request.COOKIES,
            ), file=_sys.stderr, flush=True)
        except Exception as exc:
            print('TDWDIAG callback get log failed: %r' % exc, file=_sys.stderr, flush=True)
        resp = super().get(request)
        print('TDWDIAG callback get done -> %s authed=%s' % (
            getattr(resp, 'url', resp), getattr(getattr(self, 'user', None), 'is_authenticated', None),
        ), file=_sys.stderr, flush=True)
        return resp

    def login_success(self):
        # self.user is set by the parent after a successful auth().
        from django.contrib import auth

        user = self.user

        # Set the active organization (LS pages require it), mirroring
        # users.views.user_login.
        try:
            from organizations.models import Organization

            org = Organization.find_by_user(user)
            if org is not None and user.active_organization_id != org.pk:
                user.active_organization_id = org.pk
                user.save(update_fields=['active_organization'])
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning('TDW OIDC: could not set active_organization: %s', exc)

        response = super().login_success()

        # CRITICAL (signed_cookies sessions): mozilla-django-oidc replaces the
        # request.session object mid-request to "reload" it from the store. With
        # Label Studio's SESSION_ENGINE=signed_cookies there is NO store, so the
        # auth keys written by auth.login() can be lost from the session object
        # that is finally serialized into the cookie (observed: the post-login
        # cookie had `uid`/`organization_pk` but NOT `_auth_user_id`). Re-assert
        # the login on the CURRENT request.session, exactly like LS's native
        # user_login (ModelBackend path), so _auth_user_id/_backend/_hash are
        # guaranteed to be in the cookie that goes back to the browser.
        try:
            auth.login(self.request, user, backend='django.contrib.auth.backends.ModelBackend')
            self.request.session['keep_me_logged_in'] = True
            self.request.session.modified = True
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning('TDW OIDC: re-login failed: %s', exc)

        import sys as _sys
        print('TDWDIAG login_success: user=%s authed=%s auth_user_id=%s backend=%s' % (
            getattr(user, 'email', None),
            getattr(user, 'is_authenticated', None),
            self.request.session.get('_auth_user_id'),
            self.request.session.get('_auth_user_backend'),
        ), file=_sys.stderr, flush=True)
        return response

    def get_success_url(self):
        return getattr(settings, 'LOGIN_REDIRECT_URL', '/') or '/'
