# HouseLens · Billericay

An installable, mobile-first **Progressive Web App** for a couple assessing home affordability near **Billericay railway station**. It is a real project, not a once-off spreadsheet export. The market data is refreshed **twice a week** by GitHub Actions, stored as dated snapshots, and published to GitHub Pages.

**Current status: deployable source code for HouseLens v1.3.** The included `web/data/state.json` is a pre-deployment starting reference, not a live snapshot. If updating your existing published repository, apply the v1.3 patch **without copying this file over your live saved data**. Live updating depends on the configured GitHub workflow.

## What works in this version

- Responsive, installable website; Overview, Properties, Outlook, Assumptions tabs; offline app shell; 5-year/full Bank Rate history control and source-freshness audit.
- Live *modelled* household income, mortgage repayment and mortgage/take-home calculations in the browser. Your personal inputs are kept in device localStorage, not uploaded to GitHub.
- Official daily BoE `IUDBEDR` Bank Rate series starting in 1984; short-end OIS forwards and inflation-linked gilt breakevens from BoE published Excel ZIP, refreshed automatically by the scheduled importer.
- SONIA basis-adjusted 3, 6 and 12 month **market-implied** rate proxies; explicit cheaper-or-more-expensive monthly scenario comparison; **Bank Rate + 0.50 percentage points** model mortgage rate.
- Basildon HPI (monthly, **local authority, not the 0.75-mile station radius**) refreshed from HM Land Registry CSV. This is a broad-area market benchmark.
- **New in v1.3:** CM12 0-sector (fallback CM12 district) year-on-year completed-sales medians for detached and semi-detached houses, independently calculated from HM Land Registry Price Paid Data. The importer automatically selects the necessary calendar-year files across the New Year, including 2027. These are wider postcode geographies; Land Registry Price Paid Data does not identify bedrooms, floor area, or end-of-terrace homes. These observations are **not** called matching listings.
- PropertyData `/prices` sample of nearby for-sale asking prices, with strict local filters and current-page links. Requires `PROPERTYDATA_API_KEY`; **not a comprehensive listing feed**. PropertyData's public docs explicitly state no general property listings feed is available. End-terrace homes are only included if explicitly identified, so valid listings can be missed.
- Forecasts deliberately unavailable when an essential data source fails; automatic source freshness tracking and 60-day expiry of current property listing cache. The app marks inflation *unavailable* when the relevant gilt data contain no usable tenor, rather than incorrectly marking a downloaded but empty series current.
- A history of dated market snapshots and the data release date of each source (not falsely labelled as 'new' twice weekly).

## Hard-coded buying criteria

- 3 or more bedrooms
- Detached, semi-detached, or **explicitly described** end-of-terrace
- Asking price £450,000 to £600,000, inclusive
- Within **0.75 miles straight-line** of Billericay station at `51.628884, 0.418630` (postcode CM12 0BP)
- Exclude SSTC listings where that flag is supplied

### Household examples (editable on each device)

- Total £120,000 gross split **£60,000 / £60,000 provisionally**
- Person 1: £1,000/month salary sacrifice and **Plan 2 student loan provisionally**
- Person 2: £450/month salary sacrifice and £500/month share scheme (post-tax by default; can change)
- 15% deposit and 25-year repayment term (to align with the video's primary example); house price £525,000, model mortgage = Bank Rate +0.50 pp
- Tax, National Insurance and student loan rules currently represent **England 2026/27**. The app labels this as an approximation; tax thresholds must be reviewed for the next tax year. Do not treat as a lender affordability check.

## Run locally on Windows / macOS / Linux

On Windows, double-click `RUN-ON-WINDOWS.bat` once Python is installed. Or run `python run_local.py` on Windows, macOS or Linux; it opens the app in your browser automatically.

```bash
# Requires Python 3.12+; no Node, database or server infrastructure required
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
# Optional JavaScript model tests, with Node installed
node tests/test_calculations.js
# From repository root, serve the PWA
python -m http.server 8000 --directory web
# Visit http://localhost:8000 (in Chrome or Edge)
```

The website is immediately viewable, using a labelled **verified but not live-updated** starting Bank Rate and no invented listings or forecast data. `localhost` browser installation works; non-local network hosting needs HTTPS (GitHub Pages automatically supplies this).

## Connect public live data and refresh

First run from a computer with internet:

```bash
python -m update.main
# To include property sample, set PROPERTYDATA_API_KEY in environment before running.
```

The script requests official BoE series and the current BoE published yield-curve ZIP and HM Land Registry UK HPI CSVs. It independently downloads the necessary Land Registry **annual Price Paid Data** files and derives CM12 completed-sales comparisons. The first refresh may download over 100 MB and take longer; subsequent refreshes reuse retained CM12 records and periodically check for revisions. It also extracts a BoE guidance sentence when the page contains a clearly recognisable official expectation; otherwise that component remains unavailable. A failed source never substitutes a fabricated observation. Each source's latest successful observations persist independently.

## Turn on *unattended* twice-weekly updates (GitHub Pages)

1. Create your own GitHub repository and upload **the contents** of this project folder (not the ZIP itself). Avoid putting personal financial data or API keys in the repository.
2. In repo **Settings → Pages**, choose **Source: GitHub Actions**.
3. If using PropertyData, create an API subscription and add the key to **Settings → Secrets and variables → Actions → New repository secret**, named exactly `PROPERTYDATA_API_KEY`. Leave it unset if you do not have a subscription: public rate and HPI updates still work.
4. Open **Actions → Refresh HouseLens market data and deploy → Run workflow** for the first run. Check logs and the GitHub Pages deployment URL. The schedule thereafter runs **Tuesdays & Fridays at 08:00 UTC** (09:00 UK summer time). GitHub-hosted scheduled tasks can sometimes start late or be skipped; monitor the visible 'last updated' date.
5. Open the Pages URL on your phone, then in Chrome use **Add to Home screen**, or on iPhone Safari **Share → Add to Home Screen**.

**Note:** GitHub Pages hosts a public site. Device-specific financial preferences remain local. If you want private access, use authenticated hosting rather than making a repo containing personal data.

## Future forecasting methodology & caveats

At horizon `t` = 3, 6, 12 months:

- Policy proxy = BoE short-end OIS instantaneous forward at `t` + today's `(Bank Rate - SONIA)` gap (this assumes that gap remains constant).
- Model repayment rate = policy proxy + **0.50 pp**. Actual fixed mortgage rates depend on swaps, lender margin, LTV, fees and product term.
- Example projected asking price = example home price × `(1 + monthly price trend)^t`, where price trend comes from six or more dated matching-property snapshots spanning at least 35 days; otherwise it uses a clearly-labelled CM12 0/CM12 **completed-sales year-on-year median comparison** when sample sizes suffice; otherwise the most recently published Basildon HPI annual change. These historical indicators are illustrative scenarios, **not forecasts guaranteed to materialise**; monthly change is clipped to ±2%.
- Local asking-price median changes can be strongly affected by **changing property mix and low sample sizes**. Broad-area HPI is only a stopgap proxy, **not a reliable Billericay forecast**. The app does not promise that waiting will be better. Future improvements should add matched-home repeat-listing analysis and uncertainty bands.
- 1-year gilt breakeven inflation is **RPI-linked and incorporates risk/liquidity premia**, not a CPI inflation forecast. BoE narrative is presented separately.
- Mortgage/take-home affordability = amortised repayment ÷ estimated after-tax household monthly cash pay.

## Important provider licence and data freshness

PropertyData's licensing permits historical dated observations indefinitely as part of app history, but any information presented as *current* must be refreshed within 60 days. The app removes current listings after this limit. The script never includes the API key in saved JSON or public source. Image URLs are intentionally not displayed because PropertyData does not license listing photographs. Read the [PropertyData licensing terms](https://propertydata.co.uk/api/documentation/licensing) before using a paid feed.

**It is intentionally not possible to guarantee full coverage of all station-radius properties from the `/prices` sample.** The alternative is a separately licensed comprehensive listings feed from portals or an authorised data partner; swapping providers will require a new adapter.

## Project layout

```
web/                Static installable web app, local-only household preferences
web/data/state.json Official feed observations, dated local property summaries
update/feeds.py     UK official-source and optional PropertyData adapters
update/main.py      Source failures, expiry, retention and snapshot history
update/local_sales.py  Year-round CM12 completed-sales importer from HM Land Registry PPD
.github/workflows/refresh.yml  Twice weekly GitHub Actions refresh + Pages deploy
requirements.txt    Python parsing dependency
 tests/             Backend and front-end calculation regression tests
```

## Next milestones

This **first version is not the entire finished product**. Still to implement: comprehensive authorised station-area listings coverage; backtested forecasts with uncertainty intervals; ONS historical regional earnings and the video-style combined affordability rankings; automatically versioned PAYE/tax-year rules after 2026/27; user authentication or private hosting if wanted; monitoring and alerts when a data source breaks. The supplied video/spreadsheet are *not read by the running app*.

### Source references

- [BoE Bank Rate and SONIA series help](https://www.bankofengland.co.uk/boeapps/database/help.asp)
- [BoE short-end OIS & gilt inflation curves](https://www.bankofengland.co.uk/statistics/yield-curves)
- [HM Land Registry UK HPI](https://www.gov.uk/government/collections/uk-house-price-index-reports)
- [HM Land Registry Price Paid Data yearly files](https://www.gov.uk/government/statistical-data-sets/price-paid-data-yearly-file)
- [PropertyData pricing and API documentation](https://propertydata.co.uk/api/documentation/prices)
- [PropertyData licensing and caching](https://propertydata.co.uk/api/documentation/licensing)
- [GOV.UK 2026/27 income tax](https://www.gov.uk/income-tax-rates)
- [GOV.UK 2026/27 student-loan thresholds](https://www.gov.uk/repaying-your-student-loan/what-you-pay)
