import { test, expect, Page } from '@playwright/test';

/**
 * TDW default validation E2E — proves a REAL Cognito SSO login by using the
 * resulting authenticated session to create a Label Studio project and assert
 * it exists, then cleans it up.
 *
 * This is the canonical "does the whole thing actually work" test:
 *   1. Log in through the Cognito hosted UI (real creds).
 *   2. Assert we land authenticated (NOT back on /user/login/).
 *   3. Confirm identity via /api/current-user/whoami (200 + our email).
 *   4. Create a project via the LS API using the browser's authenticated
 *      session + CSRF token, assert it is listed, then delete it.
 *
 * Requires real creds (set in env). Skips cleanly if absent so the
 * credential-free UI tests in sso.spec.ts still run in CI.
 *
 *   TEST_SSO_EMAIL=wamaya@tdw.group TEST_SSO_PASSWORD='...' \
 *   LS_URL=https://labelstudio.dev-spectrum.tdwanalytics.co \
 *   npx playwright test demo-project.spec.ts
 */

const EMAIL = process.env.TEST_SSO_EMAIL;
const PASSWORD = process.env.TEST_SSO_PASSWORD;

async function ssoLogin(page: Page) {
  await page.goto('/oidc/authenticate/');
  await page.waitForURL(/amazoncognito\.com/, { timeout: 20_000 });
  await page.locator('input[name="username"]:visible').first().fill(EMAIL!);
  await page.locator('input[name="password"]:visible').first().fill(PASSWORD!);
  await page
    .locator('input[name="signInSubmitButton"]:visible, input[type="Submit"]:visible, button[type="submit"]:visible')
    .first()
    .click();
  // Back on Label Studio, authenticated.
  await page.waitForURL(/dev-spectrum\.tdwanalytics\.co\/(?!user\/login)/, { timeout: 30_000 });
}

function csrfFrom(cookies: { name: string; value: string }[]): string {
  const c = cookies.find((x) => x.name === 'csrftoken');
  return c ? c.value : '';
}

test.describe('Cognito SSO → create a demo project', () => {
  test.skip(!EMAIL || !PASSWORD, 'TEST_SSO_EMAIL/PASSWORD not set — skipping authenticated E2E');

  test('logs in, lands authenticated, and whoami returns our user', async ({ page }) => {
    await ssoLogin(page);

    // Not bounced back to the login page.
    await page.goto('/projects/');
    await expect(page).not.toHaveURL(/\/user\/login\//);

    // Identity confirmed server-side.
    const who = await page.request.get('/api/current-user/whoami');
    expect(who.status()).toBe(200);
    const me = await who.json();
    expect((me.email || '').toLowerCase()).toBe(EMAIL!.toLowerCase());
  });

  test('creates a demo project via the authenticated session and asserts it exists', async ({ page, context }) => {
    await ssoLogin(page);

    const name = `TDW E2E Demo ${Date.now()}`;
    const cookies = await context.cookies();
    const csrf = csrfFrom(cookies);

    // Create the project using the browser's authenticated session.
    const created = await page.request.post('/api/projects', {
      headers: {
        'X-CSRFToken': csrf,
        'Content-Type': 'application/json',
        Referer: page.url(),
      },
      data: {
        title: name,
        description: 'Created by the TDW SSO end-to-end validation test.',
        label_config:
          '<View><Text name="text" value="$text"/><Choices name="sentiment" toName="text"><Choice value="Positive"/><Choice value="Negative"/></Choices></View>',
      },
    });
    expect(created.status(), `create project failed: ${created.status()} ${await created.text()}`).toBeLessThan(300);
    const project = await created.json();
    expect(project.id).toBeTruthy();

    try {
      // Assert it is listed for our user.
      const list = await page.request.get('/api/projects?page_size=100');
      expect(list.status()).toBe(200);
      const body = await list.json();
      const items = Array.isArray(body) ? body : body.results || [];
      const found = items.find((p: any) => p.id === project.id || p.title === name);
      expect(found, 'newly created project should appear in /api/projects').toBeTruthy();

      // And its detail endpoint resolves.
      const detail = await page.request.get(`/api/projects/${project.id}`);
      expect(detail.status()).toBe(200);
      expect((await detail.json()).title).toBe(name);
    } finally {
      // Clean up so the test is idempotent.
      const del = await page.request.delete(`/api/projects/${project.id}`, {
        headers: { 'X-CSRFToken': csrf, Referer: page.url() },
      });
      expect([200, 204]).toContain(del.status());
    }
  });
});
