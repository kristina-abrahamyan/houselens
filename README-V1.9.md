# HouseLens v1.9 — Refresh from the app

This **upgrade** is for the deployed HouseLens v1.8 repository `kristina-abrahamyan/houselens`.

## What changed

- **Refresh data** button in the header opens the new refresh controls in **Properties**.
- **Check latest snapshot** reloads the latest data that GitHub has *already* published. It works immediately, without any extra service or credentials.
- **Refresh economic data** can start a new Bank of England / ONS / HM Land Registry collection and deployment, when the protected Worker is configured.
- **Refresh including homes** can request an additional RealtyAPI property search as well, using free-tier API credits.
- While a manual workflow is running, HouseLens reports queued / running / completed status, using the GitHub workflow run ID where available.
- No API key or GitHub token is included in the public website. The private refresh code is **kept in memory only** and must be entered again after the browser tab closes.
- Scheduled GitHub updates continue independently: economics and inflation every 6 hours; property searches Tuesday and Friday at 08:00 UTC.

## 1. Install this upgrade (Windows)

From PowerShell in your existing `billericay-affordability` folder:

```powershell
git pull --rebase origin main
```

Extract the ZIP and copy **the contents** of its `HouseLens_v1_9_upgrade` folder over the existing project, preserving the folder structure. It contains `.github`, `web`, `worker` and `tests`. This upgrade deliberately **does not include `web/data/state.json`**. Do not delete or replace your existing saved data or secrets.

Run:

```powershell
python -m unittest discover -s tests -v
node tests/test_calculations.js
node tests/test_listing_filters.js
node tests/test_refresh_worker.mjs

git add .github/workflows/refresh.yml web/app.js web/index.html web/styles.css web/sw.js web/refresh-config.js worker/refresh-worker.mjs tests/test_refresh_worker.mjs README-V1.9.md
git commit -m "Add protected in-app refresh controls"
git push origin main
```

If the `README-V1.9.md` file stays inside the extracted `HouseLens_v1_9_upgrade` folder rather than your project root, copy it to the project root too before running `git add`.

Once GitHub deploys, the **Check latest snapshot** button will work. The two **Refresh...** buttons will deliberately remain disabled until the one-time protected Worker setup below is complete.

## 2. One-time secure setup for genuine data collection from the button

GitHub Pages is a static public website. It cannot safely hold a GitHub token. The included tiny **Cloudflare Worker** acts as a secure bridge between your website and GitHub Actions; its free plan is sufficient for occasional personal use, subject to Cloudflare's current terms/limits.

### A. Create a narrowly scoped GitHub token

1. Open: https://github.com/settings/personal-access-tokens/new
2. Enter a name such as `HouseLens refresh bridge`.
3. Choose a token expiration (note its expiration date: when it expires, the manual refresh button will need a renewed token; the independent scheduled refresh continues).
4. Under **Repository access**, select **Only select repositories**, then `houselens`.
5. Under **Repository permissions**, set **Actions: Read and write**. Leave all other optional permissions at the lowest available level.
6. Generate the token and copy it **privately**. Never put it in your public repository, `web/refresh-config.js`, screenshots, or this chat.

The GitHub API requires **Actions: write** for workflow dispatch; the Worker also needs to read run statuses.

### B. Create a Cloudflare Worker

1. Sign up / sign in at https://dash.cloudflare.com/ and open **Workers & Pages**.
2. Select **Create application → Create Worker**. Deploy the starter Worker.
3. Open its **Edit Code** view. Replace the starter script with the complete code from `worker/refresh-worker.mjs` and deploy.
4. In **Settings → Variables and Secrets**, add **two Secret** values (not plaintext variables):
   - `GITHUB_TOKEN` — your fine-grained GitHub token from A.
   - `REFRESH_ACCESS_CODE` — a **different**, random secret access code with **at least 24 characters** (longer is better). You choose this yourself and keep it private. **Do not use your GitHub token as the access code.**
5. Select **Deploy** to apply the secret changes.
6. Copy your Worker's public HTTPS URL, which will look something like `https://houselens-refresh.your-account.workers.dev`.

The Worker accepts authenticated requests **only** from the configured website origin `https://kristina-abrahamyan.github.io`, is fixed to your `houselens` repository, and rejects duplicate or very frequent manual refreshes. It does not expose the token to the website.

### C. Connect the website to the Worker

Open `web/refresh-config.js`. Change **only** the URL, e.g.:

```js
window.HOUSELENS_REFRESH_ENDPOINT = 'https://houselens-refresh.your-account.workers.dev';
```

**Put the public Worker URL there, never the GitHub token or access code.**

```powershell
git add web/refresh-config.js
git commit -m "Enable protected HouseLens refresh"
git push origin main
```

## 3. Using the button

1. Open your HouseLens website and choose **Refresh data** in the header.
2. The **Check latest snapshot** button is always available and consumes **no API credits**.
3. To collect new data on demand, enter the private **REFRESH_ACCESS_CODE** in the unlocking field. It is used only in this browser tab.
4. Select **Refresh economic data** for Bank of England, ONS and Land Registry data, or **Refresh including homes** if you also want another RealtyAPI listing search (consumes API credits).
5. HouseLens reports GitHub's queued/running/completed status. A green GitHub workflow only means deployment succeeded: check the source tracker for missing or stale individual data series.

If you don't want a Cloudflare account, skip section 2. The website still receives the **scheduled** updates and you can use **Check latest snapshot**; you simply cannot trigger new source collection from the public site without some protected server-side component.

## Important limitations and security

- **Never commit** any GitHub token, RealtyAPI key or Worker access code to the repository. Do not paste them into support screenshots.
- Your financial assumptions are still saved on the local device only (not synced across phones).
- The refresh button **does not make missing source observations appear**. Sources publish on their own schedules; the app shows the newest publication it has collected and should flag unavailable/stale values.
- RealtyAPI coverage and its right to redistribute third-party property listings are not guaranteed. Refreshing it uses API credits.
- Billericay is still the hard-coded geographic analysis area. Support for Shenfield/any location and automatically updating UK payroll tax rules remain separate engineering tasks.
- A personal access token can expire or be revoked. Renew it in the Cloudflare Worker secret before it expires; the built-in scheduled refresh uses GitHub's automatic workflow token and does not rely on this personal token.
- Automated tests verify the local JavaScript and Python code, including mock GitHub API interactions. A real end-to-end Worker call requires your account credentials and must be tested after deployment.

Reference docs:
- GitHub fine-grained tokens: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- GitHub workflow dispatch: https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event
- Cloudflare Worker dashboard: https://developers.cloudflare.com/workers/get-started/dashboard/
- Cloudflare Worker secrets: https://developers.cloudflare.com/workers/configuration/secrets/
