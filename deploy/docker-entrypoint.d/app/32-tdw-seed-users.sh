#!/usr/bin/env bash
# TDW: seed the initial Label Studio users + roles on app boot.
# Runs via the upstream docker-entrypoint.d/app/ hook chain, right AFTER
# 30-run-db-migrations.sh (so the schema — incl. our migration 0007 role — exists)
# and 31-run-label-studio-init.sh. Idempotent: safe every boot.
set -e

echo "[tdw] seeding users/roles (tdw_seed_users)"
/label-studio/.venv/bin/python /label-studio/label_studio/manage.py tdw_seed_users || {
  echo "[tdw] tdw_seed_users failed (non-fatal) — continuing boot"
}
