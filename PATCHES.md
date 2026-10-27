# PATCHES.md — TDW divergence from upstream Label Studio

Authoritative list of **every change** this fork makes on top of
`HumanSignal/label-studio`. Keep it current — edit this file in the SAME commit
as any patch change. It makes merging a new upstream release a short, known list
of conflict points.

**Base upstream tag: `1.23.2`** (Python 3.13, Django 5.2, Poetry).

All TDW changes are **additive and feature-flagged** behind `TDW_OIDC_ENABLED`
(default `false`). Flag off → the fork behaves exactly like upstream.

---

## Patch set: Cognito OIDC SSO + Postgres role model

| # | File | Change | Type |
|---|------|--------|------|
| 1 | `pyproject.toml` + `poetry.lock` | add `mozilla-django-oidc (>=4.0.0,<5.0.0)` | dep add |
| 2 | `label_studio/core/tdw_roles.py` | **NEW** — role vocab (owner/manager/reviewer/annotator) + helpers (`is_management`, `role_for_user`, `set_role`) | new file |
| 3 | `label_studio/core/auth/__init__.py` + `tdw_oidc.py` | **NEW** — `TDWCognitoOIDCBackend` (claims→User→single Org→role; owner→is_staff/superuser) | new files |
| 4 | `label_studio/organizations/models.py` | add `role` CharField to `OrganizationMember` (marked block) | small insert |
| 5 | `label_studio/organizations/migrations/0007_tdw_organizationmember_role.py` | **NEW** — migration for the role column (deps on `0006`) | new file |
| 6 | `label_studio/core/settings/base.py` | append TDW OIDC settings block (backend, `OIDC_*` from `OIDC_OP_DOMAIN`, group-role map, Cognito pool/region); register `core.tdw_context.tdw_context` processor; gated on `TDW_OIDC_ENABLED` | insert + append |
| 7 | `label_studio/core/tdw_context.py` | **NEW** — context processor exposing `tdw_oidc_enabled` to templates | new file |
| 8 | `label_studio/core/urls.py` | mount `/oidc/` + `/tdw/roles/` when enabled (marked block) | small insert |
| 9 | `label_studio/users/tdw_roles_view.py` | **NEW** — `/tdw/roles/` mini admin page (owner/manager only); saving writes Cognito groups via boto3 then updates local role | new file |
| 10 | `label_studio/users/templates/tdw/roles.html` | **NEW** — the roles page template | new file |
| 11 | `label_studio/users/templates/users/user_login.html` | add "Sign in with SSO" button (marked block) | template insert |
| 12 | `label_studio/users/management/commands/tdw_seed_users.py` | **NEW** — seed `wamaya@tdw.group=owner`, `info@tdw.group=annotator` (idempotent) | new file |
| 13 | `README.tdw.md`, `PATCHES.md` | fork docs | docs |

> Substantive logic lives in NEW TDW-owned files (upstream never touches them).
> Edits to upstream-owned files (`organizations/models.py`, `core/settings/base.py`,
> `core/urls.py`, `user_login.html`) are small inserts wrapped in
> `# --- TDW OIDC (begin/end) ---` markers — easy to re-locate on rebase.

---

## Conflict-resolution guide (merging a new upstream release)

- `base.py` — our block is self-contained, guarded by `if TDW_OIDC_ENABLED:` +
  `AUTHENTICATION_BACKENDS` append + the one context-processor line. Re-locate if
  settings moved; no ordering deps beyond `AUTHENTICATION_BACKENDS` existing first.
- `urls.py` — our `path('oidc/', ...)` + `path('tdw/roles/', ...)` just need to be
  inside the root urlpatterns.
- `user_login.html` — if upstream redesigns login, re-add the SSO anchor to
  `/oidc/authenticate/` (keep the current button CSS class).
- `organizations/models.py` — the `role` field is a marked block; re-add if the
  model is rewritten. Migration `0007` may need its `dependencies` bumped to the
  newest organizations migration.
- `core/auth/tdw_oidc.py`, `core/tdw_roles.py`, etc. — our files; only break if the
  `User`/`Organization`/`OrganizationMember` API changes. Re-verify
  `create_user`/`add_user`/`create_organization` + `deleted_at` filters.

## Verification checklist after any upstream sync (run on `dev` before PR to `main`)
1. `TDW_OIDC_ENABLED=false` → app boots, local login works (upstream parity).
2. `TDW_OIDC_ENABLED=true` → `manage.py check` = no issues; `/user/login/` shows the SSO button.
3. SSO → Cognito hosted UI → callback → a NEW Cognito user becomes a Label Studio
   `User` with an `active_organization` + role from its groups, can open a project.
4. Second login of the same user → no duplicate User/membership; role re-synced.
5. `/tdw/roles/` (as owner/manager) sets a role → Cognito group updated + local row updated.
6. arm64 image builds natively (no QEMU) and boots.

### Last validated
Base `1.23.2`, Python 3.13 / Django 5.2.17: `manage.py check` clean, migrations
apply (incl. `0007`), `tdw_seed_users` produced
`[('wamaya@tdw.group','owner'),('info@tdw.group','annotator')]`.
