# HouseLens v1.7.2 — RealtyAPI response parser and refresh diagnostics

This is a **small upgrade for your existing HouseLens v1.7 / v1.7.1 repository**, not a full replacement app.

## What it corrects

- The v1.7 RealtyAPI importer assumed every successful HTTP response contained `properties`, `results` or `listings` at the top of the payload or in one `data` wrapper. The provider's public docs don't guarantee a single response shape. The importer now accepts several commonly used nested wrappers, for example `data.results.properties` and `response.data.listings`, without inventing results.
- A `200 OK` response containing an explicit API error, invalid credential or quota warning is not treated as "no houses found".
- If the JSON is still unrecognised, the **GitHub Actions log shows only JSON field names** (not values, listing addresses, API tokens or response bodies) so the next fix can be based on evidence.
- The v1.7.1 stale-provider fix is included again: an unsuccessful RealtyAPI update clears old Untera diagnostics and does not show old listings as if they were current.
- Keeps your twice-weekly Tuesday/Friday 08:00 UTC schedule, interest rates, inflation and historical market data. Upgrades the installed website shell cache.

**Limits:** We cannot verify the private RealtyAPI response with your actual key from this package. Offline tests pass; the next live GitHub Actions run will tell us whether the provider format is now supported, or identify the remaining mismatch safely. RealtyAPI remains an unofficial Rightmove service; completeness and republication permissions are unverified.

## Install (Windows PowerShell)

1. In your existing local `billericay-affordability` repository, run:

   ```powershell
   git pull --rebase origin main
   ```

2. Extract this ZIP. Copy its `update`, `tests` and `web` folders into the **root of the existing HouseLens project**, choosing **Replace** on conflicts. Do **not** delete or replace `web/data/state.json`. This ZIP does not contain that file or an API key.

3. Run:

   ```powershell
   python -m unittest discover -s tests -v
   node tests/test_calculations.js
   node tests/test_listing_filters.js
   git add update/main.py update/realty_listings.py tests/test_realty_listings.py tests/test_listing_refresh_status.py web/app.js web/index.html web/sw.js
   git commit -m "Fix RealtyAPI response formats and refresh diagnostics"
   git push
   ```

   If `git commit` reports *nothing to commit*, check you copied the files into the correct folder and are on `main`.

4. Your `REALTYAPI_KEY` is already present in GitHub Secrets. You **do not** need to enter it again and must not paste it into code or chat.

5. Open https://github.com/kristina-abrahamyan/houselens/actions/workflows/refresh.yml → **Run workflow** (branch `main`). Check the **Update from authoritative sources** step:

   - `Listing refresh: ok` — RealtyAPI listings were imported (not necessarily matches within 0.75 mi).
   - `Listing refresh: empty` — request succeeded but yielded no supported listings; see diagnostics.
   - `Listing refresh: failed` — inspect the `WARNING: RealtyAPI listings:` line, which now includes a safe response-shape hint where appropriate.

6. Open https://kristina-abrahamyan.github.io/houselens/ and press **Ctrl + Shift + R**. Check the **Properties** page. Never infer an empty local market from an unsuccessful provider search.

### What to share for the next check

Send only the `Listing refresh:` and `WARNING: RealtyAPI listings:` lines from the workflow, **never** the secret or a full request with authentication headers.
