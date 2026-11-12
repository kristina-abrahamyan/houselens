# HouseLens v1.7 — RealtyAPI upgrade

## Included changes

- Uses RealtyAPI's **unofficial Rightmove** `/search/bycoordinates` endpoint.
- Queries a broad station-centred geographic sample: 3 miles, £300,000–£1,000,000, 2+ bedrooms. On the website, editable filters can narrow this sample (default: £450,000–£600,000, 3+ beds, detached/semi/end-of-terrace and within 0.75 miles).
- Checks exact station distance locally for results that contain coordinates and separates unverified properties from confirmed matches.
- Removes public-site API-key input. All API requests run in GitHub Actions; the secret is never published in `web/data/state.json`.
- Preserves mortgage calculations, official economic data, CPI/gilt outlook, completed sales, and the existing **Tuesday and Friday 08:00 UTC** cron schedule.
- Adds offline RealtyAPI parsing and pagination tests. Live Billericay coverage **cannot be confirmed without a real key**. A green workflow run only confirms success if the RealtyAPI step itself reports usable results.

## Apply to your EXISTING HouseLens GitHub repository

1. In PowerShell, inside your existing local HouseLens repository:

   ```powershell
   git pull --rebase origin main
   ```

2. Extract this archive and copy the `.github`, `update`, `web`, and `tests` folders into your existing repository. Replace files with the same name. **Do not copy or overwrite `web/data/state.json`** (the archive does not contain it).

3. Run from the repository root:

   ```powershell
   python -m unittest discover -s tests -v
   node tests/test_calculations.js
   node tests/test_listing_filters.js
   git add .github/workflows/refresh.yml update/main.py update/realty_listings.py web/app.js web/index.html web/listingFilters.js web/styles.css web/sw.js tests/test_realty_listings.py tests/test_listing_filters.js
   git commit -m "Replace Untera with RealtyAPI property search"
   git push
   ```

4. On GitHub, open **Settings → Secrets and variables → Actions → New repository secret** for `kristina-abrahamyan/houselens`.

   **Name:** `REALTYAPI_KEY`

   **Secret:** Paste your own RealtyAPI key. Do **not** paste it into this chat, the public website, or a source file. You may remove the old `UNTERA_API_KEY` secret.

5. Go to **Actions → Refresh HouseLens market data and deploy → Run workflow** on `main`. Inspect the **Update from authoritative sources** log. It should list RealtyAPI listings as updated; if the provider request fails, the workflow may still deploy official economic data with a warning. Open the live website and reload the Properties tab.

## Notes and limitations

- Changing filters in the browser only filters listings already downloaded within the 3-mile/£300k–£1m/2+ bedroom search. Broader searches require changing the server-side import scope and rerunning the workflow.
- The provider's coverage is **not yet validated**, and this is an unofficial Rightmove integration. Ensure your use complies with relevant data rights and provider terms before public redistribution.
- Do not treat missing matches as proof no houses are available.
- Some Rightmove records may not contain sufficient coordinates or terrace subtype information; those will not count as verified matches.
- The free quota must be checked within RealtyAPI; the importer is capped at four pages per scheduled run to limit usage.
