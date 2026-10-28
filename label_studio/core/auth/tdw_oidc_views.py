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
from mozilla_django_oidc.views import OIDCAuthenticationCallbackView

logger = logging.getLogger(__name__)


class TDWOIDCCallbackView(OIDCAuthenticationCallbackView):
    def login_success(self):
        # self.user is set by the parent after a successful auth()
        user = self.user
        try:
            from organizations.models import Organization

            org = Organization.find_by_user(user)
            if org is not None and user.active_organization_id != org.pk:
                user.active_organization_id = org.pk
                user.save(update_fields=['active_organization'])
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning('TDW OIDC: could not set active_organization: %s', exc)

        response = super().login_success()

        # keep the session for the browser lifetime (LS default behavior)
        try:
            self.request.session.setdefault('keep_me_logged_in', True)
            self.request.session.modified = True
        except Exception:  # pragma: no cover
            pass

        logger.info(
            'TDW OIDC login_success: user=%s authed=%s active_org=%s backend=%s session_key=%s redirect=%s',
            getattr(user, 'email', None),
            getattr(user, 'is_authenticated', None),
            getattr(user, 'active_organization_id', None),
            self.request.session.get('_auth_user_backend'),
            self.request.session.session_key,
            getattr(response, 'url', None),
        )
        return response

    def get_success_url(self):
        return getattr(settings, 'LOGIN_REDIRECT_URL', '/') or '/'
