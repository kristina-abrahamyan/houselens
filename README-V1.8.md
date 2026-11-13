# HouseLens v1.8 — hands-off economic-data updates, inflation, Save button

**Apply over your existing v1.7.2 repository.** This is an upgrade, not a standalone new project.

## What changed

- Independent GitHub Actions economic-data refresh **every six hours**, every day, including future years. This checks BoE Bank Rate, SONIA/OIS yield curves, gilt-implied RPI tenor (where available), BoE CPI projections and guidance, ONS measured CPI and Land Registry HPI/local completed sales.
- RealtyAPI **property listings remain Tuesday/Friday at 08:00 UTC**, as well as on manual workflow runs, to conserve free API credits. An economic-only update **does not delete** the most recent valid listings. Existing 7-day listing freshness limit remains.
- The browser fetches the newest published snapshot at load, when you return to its tab, and every 15 minutes while open. Service-worker cache version increased.
- ONS observed monthly CPI (MM23/D7G7) and BoE **forecast** CPI displayed separately. BoE published narrative mid-year peak is displayed only when an explicit numerical statement can be extracted. Gilt-implied RPI is always separate.
- Assumptions are editable without immediately taking effect. Use **Save changes**, with validation and a visible Saved/Unsaved message. This saves to your current browser's local storage, not GitHub.
- An overdue scheduled refresh is highlighted rather than being presented as current data.

## Deploy (from your local HouseLens repository root)

1. `git pull --rebase origin main`
2. Extract this ZIP and **copy its contents** over your repository, replacing matching files. Do not delete or overwrite `web/data/state.json`.
3. Test:
   ```powershell
   python -m unittest discover -s tests -v
   node tests/test_calculations.js
   node tests/test_listing_filters.js
   ```
4. Commit + push:
   ```powershell
   git add .github/workflows/refresh.yml update/main.py update/ons_cpi.py update/cpi_projections.py web/app.js web/index.html web/styles.css web/sw.js tests/test_cpi_projections.py tests/test_ons_cpi.py
   git commit -m "Automate economic updates and inflation; add Save settings"
   git push origin main
   ```
5. Go to **Actions → Refresh HouseLens market data and deploy → Run workflow** once after deployment. Check `Update from authoritative sources` for `ONS observed CPI`, `BoE CPI projections` and `Listing refresh:`.
6. Hard refresh your live site with `Ctrl+Shift+R`. The website should show the new Save button under Assumptions and the latest ONS CPI in Future outlook.

Your existing `REALTYAPI_KEY` GitHub secret stays in place. Do not put any API keys into the ZIP or commit them.

## Accuracy and future-proofing

- The workflow **attempts** automatic import every six hours, but GitHub schedules can be delayed/skipped; external APIs and report formats can change. The browser shows observation dates and overdue warning. No static GitHub Pages website can launch a secret-protected server refresh at the exact instant every visitor opens it. A true on-demand property search or instant refresh requires a serverless backend.
- BoE CPI forecast updates follow publication of new *Monetary Policy Reports*, not six-hourly economic observations. Measured CPI is published **monthly** by ONS. Gilt-implied RPI is separate and may be unavailable when validated market curves cannot be extracted.
- For mid-2027 BoE's November 2026 report says CPI could reach **around 5%**, whereas the year-end 2027 central projection is **4%**; these are different points in time.
- The 3/6/12-month real-pound illustration still assumes a **constant CPI annual rate** for an illustrative purchasing-power comparison. It is **not** a monthly BoE projection and does not change lender repayment ratios or pay growth automatically.
- Historical official housing analysis is still specific to **Billericay / CM12**. The app has *not* been made a genuine dynamic multi-area app yet; a change to Shenfield or arbitrary UK locations needs location-aware sold-price analysis, local authority HPI, station geocoding, and an on-demand backend or set of pre-tracked places. Do not simply relabel Billericay data as Shenfield.
- Income tax, National Insurance and student loan deduction assumptions still use a **2026/27 ruleset**. For financially accurate 2028 household net-pay estimates, an independently maintained or official automatically ingested tax rules source must be added. Do not treat the 2028 net-pay model as current until that is done.
- RealtyAPI is unofficial and its availability/reuse rights and geographical coverage are not guaranteed.
