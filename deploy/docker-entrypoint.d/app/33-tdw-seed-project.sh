#!/usr/bin/env bash
# TDW: seed a DEFAULT demo project on app boot so a fresh instance doesn't show
# the empty "Heidi doesn't see any projects here!" state. Runs via the upstream
# docker-entrypoint.d/app/ hook chain, AFTER 32-tdw-seed-users.sh (so the org +
# owner exist). Idempotent: only creates a project when the org has none.
set -e

echo "[tdw] seeding default project (tdw_seed_project)"
/label-studio/.venv/bin/python /label-studio/label_studio/manage.py tdw_seed_project || {
  echo "[tdw] tdw_seed_project failed (non-fatal) — continuing boot"
}
