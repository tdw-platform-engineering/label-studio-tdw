"""TDW template context processor — exposes OIDC flags to all templates.

Keeps the login-template SSO button working without editing the upstream
user_login view. TDW-owned (conflict-free on rebase).
"""
from django.conf import settings


def tdw_context(request):
    return {
        'tdw_oidc_enabled': getattr(settings, 'TDW_OIDC_ENABLED', False),
    }
