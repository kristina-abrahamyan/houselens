HOUSELENS v1.6 — INFLATION & PROPERTY-LISTING DIAGNOSTICS
===========================================================
Upgrade your existing v1.5 repository. This ZIP contains ONLY modified/new
source and test files. It intentionally excludes web/data/state.json and all
credentials so it will NOT overwrite saved rate/sales history or your API key.

WHAT CHANGED
1. Listings coverage diagnostics: reports raw records, broad-area records
   retained, and a tally of reasons records could not be used. Diagnostics
   contain no addresses or credentials.
2. Unconfirmed residential/terraced properties appear in the 'needs checking'
   group, NOT as verified detached/semi/end-terrace. Flats and explicitly
   mid-terrace homes remain excluded. Unverified location or type never counts
   toward confirmed station-radius matches.
3. The Tuesday/Friday scheduled importer reports the same diagnostics, which
   can be inspected in the Properties section after running GitHub Actions.
4. Official Bank of England CPI central-projection importer. It discovers the
   newest published Monetary Policy Report, reads its four-quarter CPI table,
   and retains the report's publication date and source URL. If BoE format or
   availability changes, a warning is shown rather than an invented estimate.
5. Future outlook adds a separate, explicitly ILLUSTRATIVE 'today's money'
   comparison using a constant annual CPI assumption sourced from an eligible
   BoE projection. This is NOT a precise BoE monthly inflation forecast and
   is not the same as the household's mortgage / nominal take-home-pay ratio.
6. Gilt-implied RPI-linked breakeven remains separate and correctly labelled
   with its ACTUAL maturity. If no valid market tenor was extracted, it
   continues to say unavailable. RPI is not substituted for CPI.
7. Service worker cache version incremented so clients receive fresh assets.

APPLY
1. In PowerShell, open the FOLDER CONTAINING your project's .github,
   update, web and tests folders (the root of your existing Git repository).
2. Execute:
      git pull --rebase origin main
3. Extract this ZIP. Copy the contents of its update, web and tests folders
   into the corresponding folders in your repository. Replace matching files.
   Do NOT delete your existing folders or web/data/state.json.
4. In PowerShell, run:
      python -m unittest discover -s tests -v
      node tests/test_calculations.js
      node tests/test_listing_filters.js
      git add update/feeds.py update/free_listings.py update/main.py update/cpi_projections.py web/app.js web/calculations.js web/index.html web/listingFilters.js web/sw.js tests/test_feeds.py tests/test_free_listings.py tests/test_cpi_projections.py tests/test_calculations.js tests/test_listing_filters.js
      git commit -m "Add inflation outlook and listing diagnostics"
      git push
5. Open your GitHub Actions refresh workflow and choose Run workflow (main).
   This imports new figures and publishes the v1.6 website. If it reports a
   source warning, see GitHub Actions logs and the app's Source health section.
6. After success, open HouseLens and do a hard refresh (Ctrl+Shift+R).
   In the Properties section click Search now with the saved Untera key.
   Check the Coverage diagnostics paragraph; zero retained listings by itself
   is NOT evidence that there are no suitable houses for sale.
7. Check Future outlook for 'BoE CPI central projection', the illustrative
   purchasing-power comparison, and the separate gilt-implied RPI proxy.

SCHEDULE
Existing .github/workflows/refresh.yml is UNCHANGED: every Tuesday and
Friday, 08:00 UTC (09:00 BST in summer). GitHub's schedule can be delayed.
The scheduled listing importer requires the UNTERA_API_KEY repository secret;
the manually-triggered browser search uses its key stored on your device.

IMPORTANT LIMITATIONS
- Live API-provider coverage is NOT confirmed by offline tests; only an actual
  search with your Untera key can establish what it returns in Billericay.
- No annualised CPI figure should be mistaken for a month-by-month forecast.
- CPI purchasing-power adjustments do NOT assume any increase in salary.
- Asking-price snapshots and official sold-price analysis remain distinct.
- Bank Rate +0.5 percentage points is a modelling assumption, not a real
  lender mortgage offer.
