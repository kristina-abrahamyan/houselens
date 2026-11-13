# HouseLens v1.7.1 — RealtyAPI refresh diagnostics

## Why this patch exists

In v1.7, the public site was updated but the saved `state.json` could still contain the **previous Untera** records and 400-record diagnostic. The UI mislabelled these as an out-of-date RealtyAPI snapshot. A green workflow only shows the overall job completed, not that RealtyAPI successfully fetched listings.

This update:

- Rejects legacy provider data in the Properties page; never treats Untera results as RealtyAPI results.
- Distinguishes the following cases in the published data and page: **missing GitHub Actions secret**, **RealtyAPI request failed**, **RealtyAPI returned no supported results**, or **successful listings**.
- Removes stale provider diagnostics and previously retained listings on a failed or unconfigured refresh.
- Logs a clear **Listing refresh:** message under the GitHub Actions `Update from authoritative sources` step.
- Does **not** include your API key or overwrite `web/data/state.json`.
- Preserves the Tuesday/Friday 08:00 UTC automated refresh and all economic analysis.

## Install on top of v1.7

1. Open PowerShell inside your existing HouseLens repository and run `git pull --rebase origin main`.
2. Extract the ZIP, and copy its `update`, `web`, and `tests` folders into your project, replacing matching files. **Do not replace or delete `web/data/state.json`.**
3. Run:

   ```powershell
   python -m unittest discover -s tests -v
   node tests/test_calculations.js
   node tests/test_listing_filters.js
   git add update/main.py web/app.js web/index.html web/sw.js tests/test_listing_refresh_status.py
   git commit -m "Report RealtyAPI refresh status and clear legacy listings"
   git push
   ```

4. Confirm the GitHub Actions secret **`REALTYAPI_KEY`** is present under Settings → Secrets and variables → Actions. Do not paste the key into the repository or chat.
5. Run [the HouseLens workflow](https://github.com/kristina-abrahamyan/houselens/actions/workflows/refresh.yml) on branch **main**. Wait for its completion.
6. Open the run's **Update from authoritative sources** step. Locate `Listing refresh:`:
   - `ok`: provider returned supported listings (they may or may not match your tight filters)
   - `empty`: provider responded, but no supported listings were retained
   - `missing_key`: the `REALTYAPI_KEY` secret is absent/empty
   - `failed`: provider request error; read the `WARNING: RealtyAPI listings:` line immediately below
7. Open HouseLens and use **Ctrl+Shift+R**. Its Properties page must no longer show the previous Untera 400-record statistics.

### Data caveat

RealtyAPI is an unofficial Rightmove service. Availability of its API and rights to republish records require separate verification. Even an `ok` refresh does not prove comprehensive coverage. Do not interpret an empty result as proof no homes exist.
