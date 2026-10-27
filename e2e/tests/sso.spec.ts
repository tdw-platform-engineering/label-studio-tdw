import { test, expect } from '@playwright/test';

/**
 * TDW end-to-end tests against a DEPLOYED label-studio-tdw instance.
 *
 * Verifies the Cognito SSO integration as a real browser would hit it:
 *   - app is up (health), login page renders
 *   - the "Sign in with SSO" button is present on /user/login/
 *   - clicking it drives the browser to the Cognito hosted UI
 *   - the OIDC redirect uses the correct HTTPS callback + client id
 *
 * These are black-box UI tests (no secrets). A FULL login (entering Cognito
 * creds) is optional and only runs when TEST_SSO_EMAIL / TEST_SSO_PASSWORD are
 * provided, so CI can stay credential-free by default.
 */

test('health endpoint is 200', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
});

test('login page renders the Sign in with SSO button', async ({ page }) => {
  await page.goto('/user/login/');
  const sso = page.getByRole('link', { name: /sign in with sso/i });
  await expect(sso).toBeVisible();
  await expect(sso).toHaveAttribute('href', /\/oidc\/authenticate\//);
});

test('SSO button navigates to the Cognito hosted UI (https callback)', async ({ page }) => {
  await page.goto('/user/login/');
  await page.getByRole('link', { name: /sign in with sso/i }).click();
  // Lands on the Cognito hosted UI
  await page.waitForURL(/amazoncognito\.com/, { timeout: 20_000 });
  const url = new URL(page.url());
  expect(url.hostname).toContain('amazoncognito.com');
  // Correct OIDC params: https callback (ALB TLS), our client, openid scope.
  const redirect = url.searchParams.get('redirect_uri') || '';
  expect(redirect.startsWith('https://')).toBeTruthy();
  expect(redirect).toContain('/oidc/callback/');
  expect(url.searchParams.get('client_id')).toBeTruthy();
  expect(url.searchParams.get('scope') || '').toContain('openid');
});

// Optional full-login flow — only with real test creds in env.
test('full Cognito login reaches Label Studio', async ({ page }) => {
  const email = process.env.TEST_SSO_EMAIL;
  const password = process.env.TEST_SSO_PASSWORD;
  test.skip(!email || !password, 'TEST_SSO_EMAIL/PASSWORD not set — skipping full login');

  await page.goto('/oidc/authenticate/');
  await page.waitForURL(/amazoncognito\.com/);
  await page.locator('input[name="username"], input[type="email"], input[type="text"]').first().fill(email!);
  await page.locator('input[name="password"], input[type="password"]').first().fill(password!);
  await page.getByRole('button', { name: /sign in|log in/i }).first().click();
  // Back on Label Studio, authenticated (projects page / no login form).
  await page.waitForURL(/dev-spectrum\.tdwanalytics\.co/, { timeout: 30_000 });
  await expect(page).not.toHaveURL(/\/user\/login\//);
});
