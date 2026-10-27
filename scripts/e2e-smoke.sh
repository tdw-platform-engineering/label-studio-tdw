#!/usr/bin/env bash
#
# e2e-smoke.sh — end-to-end smoke test for a deployed label-studio-tdw instance.
#
# Validates the FULL deployed stack from the outside in: DNS + TLS, the health
# endpoint, the version endpoint, that the TDW SSO button is rendered on the
# login page, and that the OIDC authorize route redirects to Cognito. Optionally
# checks the ECS service + ALB target health if AWS creds + names are provided.
#
# Exit non-zero on the FIRST failure so it can gate a pipeline / be run in CI.
#
# Usage:
#   LS_URL=https://labelstudio.dev-spectrum.tdwanalytics.co ./scripts/e2e-smoke.sh
# Optional AWS checks:
#   LS_URL=... ECS_CLUSTER=dev-spectrum-label-studio ECS_SERVICE=dev-spectrum-label-studio \
#   TARGET_GROUP_ARN=arn:... AWS_REGION=us-east-1 ./scripts/e2e-smoke.sh
#
set -uo pipefail

LS_URL="${LS_URL:?set LS_URL, e.g. https://labelstudio.dev-spectrum.tdwanalytics.co}"
TIMEOUT="${TIMEOUT:-20}"
PASS=0
FAIL=0

ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
hdr()  { echo; echo "== $1 =="; }

curl_code() { curl -s -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" "$@"; }
curl_body() { curl -s --max-time "$TIMEOUT" "$@"; }

hdr "1. DNS + TLS"
if curl -s -o /dev/null --max-time "$TIMEOUT" "$LS_URL/health"; then
  ok "TLS handshake + DNS resolve to $LS_URL"
else
  bad "cannot reach $LS_URL (DNS/TLS/ALB down)"
fi

hdr "2. Health endpoint (/health)"
code=$(curl_code "$LS_URL/health")
if [ "$code" = "200" ]; then ok "/health = 200"; else bad "/health = $code (expected 200 — app not serving / no healthy ECS target)"; fi

hdr "3. Version endpoint (/version/)"
code=$(curl_code "$LS_URL/version/")
if [ "$code" = "200" ]; then ok "/version/ = 200"; else bad "/version/ = $code"; fi

hdr "4. TDW SSO button on the login page"
body=$(curl_body "$LS_URL/user/login/")
if echo "$body" | grep -qi 'Sign in with SSO'; then
  ok "login page renders the 'Sign in with SSO' button (TDW_OIDC_ENABLED is on)"
else
  bad "SSO button NOT found on /user/login/ (TDW_OIDC_ENABLED off, or vanilla upstream image deployed)"
fi

hdr "5. OIDC authorize redirects to Cognito"
# /oidc/authenticate/ should 302 to the Cognito hosted UI (amazoncognito.com)
loc=$(curl -s -o /dev/null -w '%{redirect_url}' --max-time "$TIMEOUT" "$LS_URL/oidc/authenticate/")
if echo "$loc" | grep -qi 'amazoncognito.com'; then
  ok "/oidc/authenticate/ -> Cognito ($loc)"
else
  bad "/oidc/authenticate/ did not redirect to Cognito (got: '${loc:-<none>}')"
fi

# ---- Optional AWS-side checks (only if creds + names provided) ----
if [ -n "${ECS_CLUSTER:-}" ] && [ -n "${ECS_SERVICE:-}" ] && command -v aws >/dev/null; then
  hdr "6. ECS service running"
  read -r running desired < <(aws ecs describe-services --cluster "$ECS_CLUSTER" --services "$ECS_SERVICE" \
      --query 'services[0].[runningCount,desiredCount]' --output text 2>/dev/null)
  if [ "${running:-0}" -ge 1 ] && [ "${running:-0}" = "${desired:-x}" ]; then
    ok "ECS $running/$desired tasks running"
  else
    bad "ECS running=$running desired=$desired (no healthy task)"
  fi
fi

if [ -n "${TARGET_GROUP_ARN:-}" ] && command -v aws >/dev/null; then
  hdr "7. ALB target health"
  states=$(aws elbv2 describe-target-health --target-group-arn "$TARGET_GROUP_ARN" \
      --query 'TargetHealthDescriptions[].TargetHealth.State' --output text 2>/dev/null)
  if echo "$states" | grep -qw healthy; then ok "ALB has a healthy target ($states)"; else bad "no healthy ALB target (states: ${states:-none})"; fi
fi

echo
echo "================  E2E RESULT: $PASS passed, $FAIL failed  ================"
[ "$FAIL" -eq 0 ]
