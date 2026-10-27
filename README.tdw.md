# label-studio-tdw

TDW's fork of [HumanSignal/label-studio](https://github.com/HumanSignal/label-studio),
patched to add **native AWS Cognito OIDC single sign-on** with identity mapping
into Label Studio's own `User` + `Organization` model, plus a Postgres-backed
role model and a mini role-admin page.

> Maintained fork. We diverge from upstream only where necessary (the Cognito
> OIDC integration) and keep a clean, documented patch set (`PATCHES.md`) so we
> can rebase onto new upstream releases with minimal friction.

**Base upstream tag: `1.23.2`** — Python **3.13**, Django **5.2**, Poetry build,
arm64-native multi-arch Dockerfile.

---

## 1. Branching model (READ THIS FIRST)

| Branch | Role | Rules |
|--------|------|-------|
| **`main`** | **production** — what every client deploys | **NEVER commit directly.** Only receives reviewed merges from `dev`. Clients ALWAYS build/deploy `main`. |
| **`dev`** | integration — our patches + upstream sync | All work lands here first. Upstream releases are merged here, patches re-applied/verified, then promoted to `main` via PR. |
| `upstream` (git remote) | tracking | `HumanSignal/label-studio`. New upstream releases are pulled from here into `dev`. |

```
HumanSignal/label-studio (upstream)
        │  merge a new upstream release tag
        ▼
      dev   ── our Cognito-OIDC patches live here, validated here
        │  PR, after validation
        ▼
      main  ── PROD. clients deploy THIS. never edited directly.
```

**Golden rules**
1. Never push to `main` directly. `dev → main` only, via PR, after the image builds and SSO login is verified.
2. Keep the Cognito patch isolated + documented (`PATCHES.md`) so upstream syncs stay cheap.
3. Clients deploy the `main` branch image only.

### Syncing a new upstream release (on `dev`)
```bash
git fetch upstream --tags
git checkout dev
git merge <NEW.VERSION>      # e.g. 1.24.0 — resolve the few marked patch points (see PATCHES.md)
poetry lock                  # refresh lock if pyproject changed
# re-verify OIDC login end-to-end, rebuild the arm64 image, then PR dev -> main
```

---

## 2. Why we forked

Community (free) Label Studio ships **only local username/password auth** — no
built-in OIDC/SAML (Enterprise feature), and **no per-member role** (only the
derived `is_owner`). TDW requires **Cognito SSO with identity mapping** (a Cognito
user resolves to a real Label Studio `User` + org membership + role, so work is
attributed to the SSO identity, and Cognito groups drive the role). An ALB-level
auth proxy can't do that mapping, so we patch the app.

Everything is **additive and feature-flagged** behind `TDW_OIDC_ENABLED` (default
`false` → byte-for-byte upstream behavior). See `PATCHES.md` for the exact files.

---

## 3. Cognito OIDC integration — design

Implemented with [`mozilla-django-oidc`](https://mozilla-django-oidc.readthedocs.io/).

### Roles (Postgres-backed)
`owner` > `manager` > `reviewer` > `annotator` (default `annotator`). Stored on a
new `OrganizationMember.role` column (migration `0007`). **AWS Cognito groups are
the source of truth**: the role is (re)synced from `cognito:groups` on every OIDC
login, and the `/tdw/roles/` page edits Cognito (not just the local row).

- Only `owner`/`manager` may open `/tdw/roles/` and manage people.
- `owner` additionally gets Django `is_staff`+`is_superuser`.

### Group → role mapping (configurable)
`TDW_OIDC_GROUP_ROLE_MAP` is a JSON env var, e.g.
```
{"ls-admins":"owner","ls-managers":"manager","ls-reviewers":"reviewer","ls-annotators":"annotator"}
```
Highest-privilege matching group wins; unmapped users get `annotator`.

### The custom backend — `core/auth/tdw_oidc.py::TDWCognitoOIDCBackend`
Subclasses `OIDCAuthenticationBackend`:
- `filter_users_by_claims` — find `User` by OIDC `email`.
- `create_user` — create the LS user, join the SINGLE org, sync role.
- `update_user` — keep name + role synced on each login.

### Configuration (env — nothing baked into the image)
| Env var | Purpose |
|---|---|
| `TDW_OIDC_ENABLED` | `true` to enable the whole integration (default off) |
| `OIDC_RP_CLIENT_ID` / `OIDC_RP_CLIENT_SECRET` | Cognito app-client creds |
| `OIDC_OP_DOMAIN` | Cognito hosted-UI domain (endpoints derived from it) |
| `OIDC_RP_SIGN_ALGO` | `RS256` |
| `TDW_COGNITO_USER_POOL_ID` / `TDW_COGNITO_REGION` | pool id + region (for `/tdw/roles/` writeback) |
| `TDW_OIDC_GROUP_ROLE_MAP` | JSON group→role map |
| `TDW_OIDC_DEFAULT_ORG_TITLE` | title of the single org created on first login |
| `LABEL_STUDIO_HOST` | public base URL, must match the Cognito callback |

### Seeding
`python label_studio/manage.py tdw_seed_users` (idempotent) seeds
`wamaya@tdw.group=owner`, `info@tdw.group=annotator`. Override via `TDW_SEED_USERS`
(JSON). Run at container start on a fresh DB.

---

## 4. Build & deploy

Clients deploy **`main`**. The image is built **natively on arm64 / Graviton**
(no QEMU emulation) — either in CI on an arm CodeBuild runner, or on the target
`t4g` EC2 during Ansible convergence — and pushed to the client's own ECR.
Runtime wiring (RDS, S3 media, Cognito, domain) is environment-driven; secrets
come from SSM/Secrets Manager via the EC2 instance role, never baked in. See the
`terraform-v3` repo: `modules/label-studio`, `ansible/label-studio`,
`clients/spectrum/dev/002-LabelStudio`.

### Validation status
The patch set was validated on the real base (Python 3.13 / Django 5.2.17):
`manage.py check` = no issues, migrations apply (incl. `0007` role), and
`tdw_seed_users` creates `wamaya=owner` / `info=annotator` with the role column
populated. See `PATCHES.md` for the per-sync verification checklist.

---

## 5. Upstream

Original: https://github.com/HumanSignal/label-studio (Apache-2.0). See `LICENSE`
/ `NOTICE`. Our additions are tracked in `PATCHES.md`.
