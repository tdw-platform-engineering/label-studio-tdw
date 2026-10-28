# PATCHES.md — `label-studio-tdw` divergence from upstream

Fork of **HumanSignal/label-studio `1.23.2`** (Django 5.2, Python 3.13, Poetry).
Everything the TDW fork changes is **feature-flagged on `TDW_OIDC_ENABLED`** — when
that env var is not `true`, the app behaves exactly like upstream. The fork adds
native **AWS Cognito OIDC single sign-on** with **group → role** mapping persisted
in Postgres (`owner`/`manager`/`reviewer`/`annotator`).

Upstream remote is kept (`git remote add upstream https://github.com/HumanSignal/label-studio`)
so the fork can rebase onto future releases. Branches: `main` = prod (clients
deploy this image), `dev` = integration; promote `dev → main` via PR.

> Regenerate this file's accuracy with:
> `git diff --name-status <first-tdw-commit>~1 HEAD`

---

## Added files (new, TDW-owned — upstream never edits these)

| Path | Purpose |
|---|---|
| `label_studio/core/auth/__init__.py` | Makes `core.auth` a package. |
| `label_studio/core/auth/tdw_oidc.py` | **`TDWCognitoOIDCBackend`** (subclasses `mozilla_django_oidc` backend). Resolves the OIDC `email` → LS `User` (creates on first login), attaches the single community org, maps `cognito:groups` → TDW role on `OrganizationMember.role`, sets `is_staff`/`is_superuser` for `owner`. `get_userinfo()` **merges `cognito:groups` from the verified ID token** (Cognito's `/oauth2/userInfo` omits that claim). `authenticate()` accepts pre-exchanged tokens (`tdw_token_info`) from the custom callback so the auth code is not double-spent. |
| `label_studio/core/auth/tdw_oidc_views.py` | **`TDWOIDCAuthenticateView`** (reuses mozilla's authorize-request view) and **`TDWOIDCCallbackView`** — a *self-contained* Authorization-Code callback that exchanges the code for tokens, authenticates via the backend, sets `active_organization`, performs ONE clean `auth.login(..., ModelBackend)`, and sets **`session['last_login']`** (see gotcha #5). Replaces the stock mozilla callback (whose mid-request `request.session` reassignment lost the auth keys under LS's session stack). |
| `label_studio/core/tdw_roles.py` | Framework-agnostic role vocabulary (`owner`/`manager`/`reviewer`/`annotator`), rank ordering, `normalize_role`, `set_role`, and a permission helper. Single source of truth for role logic. |
| `label_studio/core/tdw_context.py` | Template context processor exposing `tdw_oidc_enabled` so login templates can conditionally render the SSO button. |
| `label_studio/organizations/migrations/0007_tdw_organizationmember_role.py` | Migration adding the `role` CharField to `OrganizationMember`. |
| `label_studio/users/tdw_roles_view.py` | `/tdw/roles/` mini admin page view — an `owner` can edit a user's role; **writes back to Cognito** (boto3 `admin_add/remove_user_from_group`) so Cognito stays the source of truth. `deleted_at`-aware. |
| `label_studio/users/templates/tdw/roles.html` | Template for the `/tdw/roles/` page. |
| `label_studio/users/management/commands/tdw_seed_users.py` | `manage.py tdw_seed_users` — seeds the initial users/roles (e.g. `wamaya@tdw.group`=owner). Idempotent. |
| `Dockerfile.tdw` | **Fast overlay build**: `FROM` a prebuilt upstream base image + `COPY label_studio/` (backend-only patch) + install `mozilla-django-oidc`. Seconds, not the 15–30 min full frontend/Poetry build. `BASE_IMAGE` defaults to a client-ECR mirror of `heartexlabs/label-studio:1.23.2`. |
| `deploy/docker-entrypoint.d/app/32-tdw-seed-users.sh` | Entry-point drop-in that runs `tdw_seed_users` on boot **after** upstream's `30-run-db-migrations.sh`. |
| `e2e/` (`package.json`, `package-lock.json`, `playwright.config.ts`, `.gitignore`, `README.md`, `tests/sso.spec.ts`, `tests/demo-project.spec.ts`) | **Playwright E2E** against a deployed instance: health, SSO button, Cognito redirect (https callback), and the **default validation** — full Cognito login → create a demo project → assert it exists → clean up. Credential-free tests run in CI; the authenticated tests run when `TEST_SSO_EMAIL`/`TEST_SSO_PASSWORD` are set. |
| `label_studio/tests/test_tdw_oidc.py` | pytest unit/integration tests for the OIDC backend + role mapping (no network). |
| `scripts/e2e-smoke.sh` | Shell smoke test for the deployed stack. |
| `README.tdw.md` | Fork overview: branching model, Cognito OIDC design, build/deploy. |
| `PATCHES.md` | This file. |

## Modified files (upstream files the fork edits — keep diffs minimal + flagged)

| Path | Change |
|---|---|
| `label_studio/core/settings/base.py` | Appended the **TDW OIDC settings block** (gated on `TDW_OIDC_ENABLED`): registers `TDWCognitoOIDCBackend` in `AUTHENTICATION_BACKENDS`, derives OIDC endpoints from `OIDC_OP_DOMAIN`, builds `OIDC_OP_JWKS_ENDPOINT` from the **Cognito issuer** (not the hosted-UI domain — gotcha #1), reads `TDW_OIDC_GROUP_ROLE_MAP`, sets `SECURE_PROXY_SSL_HEADER`/`USE_X_FORWARDED_HOST` for the ALB (gotcha #2), `OIDC_STORE_ID_TOKEN=True`. Also registers the `tdw_context` processor. |
| `label_studio/core/settings/label_studio.py` | Made **`SESSION_ENGINE` env-overridable**; defaults to `django.contrib.sessions.backends.db` when `TDW_OIDC_ENABLED` (upstream hardcodes `signed_cookies`, incompatible with the OIDC callback — gotcha #3). |
| `label_studio/core/urls.py` | Mounts (gated on the flag, custom views FIRST so they win over mozilla's): `oidc/authenticate/`, `oidc/callback/`, `oidc/` (mozilla urls), and `tdw/roles/`. |
| `label_studio/core/middleware.py` | `SetSessionUIDMiddleware`: when `TDW_OIDC_ENABLED`, do **not** create/save a session for anonymous requests that don't already have one — stops the post-login anon-session cookie churn that raced with and clobbered the authenticated cookie (gotcha #4). |
| `label_studio/organizations/models.py` | Added the `role` CharField to `OrganizationMember` (paired with migration 0007). |
| `label_studio/users/templates/users/new-ui/user_login.html` | Added the **"Sign in with SSO"** button (gated on `tdw_oidc_enabled`). **This NEW-UI template is the one actually served.** |
| `label_studio/users/templates/users/user_login.html` | Same SSO button on the legacy login template (belt-and-suspenders). |
| `pyproject.toml` | Added `mozilla-django-oidc` (Django 5.2-compatible 4.x). |
| `poetry.lock` | Lockfile updated for the new dependency. |

---

## Gotchas discovered while integrating Cognito SSO (why the non-obvious patches exist)

1. **JWKS lives on the Cognito ISSUER, not the hosted-UI domain.** `mozilla-django-oidc`
   fetched `https://<hosted-ui>/.well-known/jwks.json` → **404** → post-login 500.
   Cognito serves JWKS at the issuer: `https://cognito-idp.<region>.amazonaws.com/<pool-id>/.well-known/jwks.json`.
   `base.py` builds `OIDC_OP_JWKS_ENDPOINT` from `TDW_COGNITO_REGION`/`TDW_COGNITO_USER_POOL_ID`.
2. **ALB terminates TLS → the container sees http.** Django built `http://` callback
   URLs that didn't match the Cognito app-client. Fixed with
   `SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')` + `USE_X_FORWARDED_HOST=True`.
3. **`cognito:groups` is ID-token-only.** Cognito's `/oauth2/userInfo` does not return it,
   so role mapping saw no groups and defaulted everyone to `annotator`.
   `get_userinfo()` merges the claim from the verified ID token → correct role (`owner`).
4. **`signed_cookies` sessions break the OIDC callback.** Upstream default
   `SESSION_ENGINE=signed_cookies`; mozilla's callback reassigns `request.session`
   mid-request to "reload from the store", but there is no store → `auth.login()`'s keys
   were lost from the serialized cookie. Switched to DB-backed sessions for OIDC, and
   replaced the callback with a self-contained one (single clean `auth.login`).
5. **THE login-loop root cause — `session['last_login']`.** LS's session-timeout
   middleware (`core.middleware`) logs out any authenticated session whose
   `session['last_login']` is missing (it defaults to `0`, so `now - 0` ≫ max age →
   `logout(request)` on the very next request). LS's native login sets it
   (`users/functions/common.py`); the OIDC callback must do the same. Without it, every
   SSO login bounced straight back to `/user/login/`. The callback now sets
   `request.session['last_login'] = time.time()`.
6. **Anonymous session cookie churn.** After the callback redirect, the SPA fires several
   parallel anonymous requests (`/__lsa/`, `/heidi-tips`, static); each was creating +
   saving a fresh anon session and shipping a `Set-Cookie`, the last of which clobbered
   the authenticated cookie. `SetSessionUIDMiddleware` no longer creates sessions for
   anonymous requests under OIDC.

## Deploy note (CI reliability)
The CodePipeline builds + migrates correctly, but its force-redeploy step deploys the
`:latest` tag, which **ECS/Fargate caches by digest** and does not reliably pull. Land
images by registering a task-def revision that references the image **by digest**
(`<repo>@sha256:…`) and deploying that. (Recommended follow-up: have the pipeline deploy
by the immutable commit-SHA tag so `git push` → auto-deploy is hands-off.)

## Required env (set by the Terraform 002-LabelStudio stack)
`TDW_OIDC_ENABLED=true`, `OIDC_OP_DOMAIN`, `OIDC_RP_CLIENT_ID`, `OIDC_RP_CLIENT_SECRET`
(secret), `TDW_COGNITO_USER_POOL_ID`, `TDW_COGNITO_REGION`, `TDW_OIDC_GROUP_ROLE_MAP`
(JSON), `LABEL_STUDIO_HOST`, `SESSION_COOKIE_SECURE=1`, `SESSION_COOKIE_SAMESITE=Lax`,
plus the standard `POSTGRE_*` DB vars and S3 media vars.
