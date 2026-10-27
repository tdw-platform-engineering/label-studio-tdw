# e2e — Playwright tests (deployed Cognito SSO)

Black-box browser tests against a DEPLOYED label-studio-tdw instance.

```bash
cd e2e
npm install
npm run install-browsers
LS_URL=https://labelstudio.dev-spectrum.tdwanalytics.co npm test
```

Covers: `/health`, the **Sign in with SSO** button on `/user/login/`, and the
SSO button driving the browser to the Cognito hosted UI with the correct
**https** callback + client id + openid scope.

Optional full login (enters Cognito creds) runs only when set:
```bash
TEST_SSO_EMAIL=... TEST_SSO_PASSWORD=... LS_URL=... npm test
```
