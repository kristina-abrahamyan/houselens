"""Twice-weekly scheduled snapshot refresher. Failing source != fabricated observation."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from statistics import median
from update import feeds, local_sales, realty_listings, cpi_projections

STATE_PATH = Path(__file__).resolve().parents[1] / 'web' / 'data' / 'state.json'


def refresh(state, *, now=None, adapters=feeds):
    now = now or dt.datetime.now(dt.timezone.utc)
    timestamp = now.replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    state = json.loads(json.dumps(state))
    state['lastAttempt'] = timestamp
    errs = []
    successful = []
    def run(name, callback):
        try:
            result = callback()
            successful.append(name)
            return result
        except Exception as ex:
            # Do not expose URL (may contain secret API key).
            msg = str(ex).split('?', 1)[0][:220]
            errs.append(f'{name}: {type(ex).__name__}: {msg}')
            return None

    bank = run('Bank Rate', adapters.get_bank_rate)
    if bank:
        state.update(bankRate=bank['rate'], bankRateAsOf=bank['asOf'], history=bank['history'])
        state.setdefault('sources', {})['bankRate'] = bank['sourceUrl'].split('?', 1)[0]
    sonia = run('SONIA', adapters.get_sonia)
    if sonia:
        state['soniaRate'] = sonia['rate']
        state['soniaAsOf'] = sonia['asOf']
    if bank and sonia:
        curves = run('Yield curves', lambda: adapters.get_market_curves(bank['rate'], sonia['rate']))
        if curves:
            for name in ('ois', 'gilts'):
                if name in curves:
                    state[name] = curves[name]
                    state['sources'][name] = curves[name]['sourceUrl']
            errs.extend('Yield curves: ' + warning for warning in curves.get('warnings', []))
    # Independent official quarterly CPI central projection. Never substitute
    # RPI gilt breakevens, which are a different inflation measure.
    if adapters is feeds:
        cpi = run('BoE CPI projections', lambda: cpi_projections.get_cpi_projection(feeds.fetch_bytes, today=now.date()))
        if cpi:
            state['cpiProjection'] = cpi
            state.setdefault('sources', {})['cpiProjection'] = cpi['sourceUrl']
    guidance = run('BoE guidance', adapters.get_guidance)
    if guidance:
        state['guidance'] = guidance
    hpi = run('Basildon HPI', adapters.get_hpi)
    if hpi:
        state['hpi'] = hpi
        historical = {p['date']: p for p in state.get('hpiHistory', [])}
        historical[hpi['date']] = {'date': hpi['date'], 'averagePrice': hpi['averagePrice']}
        state['hpiHistory'] = [historical[k] for k in sorted(historical)][-120:]
        state['sources']['hpi'] = hpi['sourceUrl']
    # Housemetric-style CM12 local comparables, using official sold-price
    # records only. No scraping of Housemetric and no assumption that these
    # properties satisfy the user's exact station-radius/bedroom criteria.
    if adapters is feeds:
        sales = run('CM12 completed sales', lambda: local_sales.update_local_sales(
            state.get('localSalesDataset'), today=now.date()))
        if sales:
            state['localSalesDataset'] = sales['dataset']
            state['localSales'] = sales['summary']
            state.setdefault('sources', {})['localSales'] = sales['summary']['sourceUrl']
    # RealtyAPI is optional. The server-side secret is NEVER committed to the public
    # snapshot. Keep official economics sources independent of this third party.
    key = os.environ.get('REALTYAPI_KEY', '').strip()
    if key:
        feed = run('RealtyAPI listings', lambda: realty_listings.get_realty_listings(key))
        if feed is not None:
            state['listings'] = feed['listings']
            state['listingsAsOf'] = timestamp
            state['listingProvider'] = 'RealtyAPI (unofficial Rightmove API)'
            state['listingCoverage'] = {
                'sampleSize': feed['sampleSize'], 'note': feed['coverageNote'],
                'pages': feed['pages'], 'truncated': feed['truncated'],
                'diagnostics': feed['diagnostics'],
            }
            state.setdefault('sources', {})['listings'] = feed['sourceUrl']
            matches = realty_listings.strict_default_matches(feed['listings'])
            if len(matches) >= 3:
                snapshot = {'date': now.date().isoformat(), 'observedAt': timestamp,
                    'count': len(matches), 'medianPrice': int(median(p['price'] for p in matches)),
                    'scope': 'confirmed station-radius matches from RealtyAPI; 0.75mi / 3 beds / £450k–£600k',
                    'properties': [{'id': p['id'], 'price': p['price']} for p in matches]}
                state['snapshots'] = ([entry for entry in state.get('snapshots', [])
                    if entry.get('date') != snapshot['date']] + [snapshot])[-350:]
        elif state.get('listingProvider', '').lower().find('realtyapi') < 0:
            # Never display previous Untera data under the RealtyAPI branding.
            state['listings'] = []
            state['listingsAsOf'] = None
            state['listingProvider'] = 'RealtyAPI (connection failed)'
    else:
        # A missing secret does not mean prior Untera listings are verified.
        if 'realtyapi' not in str(state.get('listingProvider', '')).lower():
            state['listings'] = []
            state['listingsAsOf'] = None
            state['listingCoverage'] = {'sampleSize': 0, 'pages': 0,
                'diagnostics': {'rawResults': 0, 'reasons': {}},
                'note': 'RealtyAPI not connected. Add the REALTYAPI_KEY GitHub Actions secret.'}
        state['listingProvider'] = 'RealtyAPI (not configured)'
        state.setdefault('sources', {})['listings'] = 'Not configured: REALTYAPI_KEY secret'
    # Never label old listings as currently for sale after a failed refresh.
    if state.get('listingsAsOf'):
        try:
            age=(now-dt.datetime.fromisoformat(state['listingsAsOf'].replace('Z','+00:00'))).total_seconds()/86400
            if age>7:
                state['listings']=[]
                errs.append('Property listing snapshot is older than 7 days: shown as unavailable')
        except (TypeError,ValueError):
            state['listings']=[]
    state['lastRun'] = timestamp if successful else state.get('lastRun')
    state['status'] = 'UPDATED' if not errs else ('PARTIAL' if successful else 'ERROR')
    state['errors'] = errs
    state['runResults'] = successful
    state['asOf'] = timestamp
    return state


def main():
    before = json.loads(STATE_PATH.read_text(encoding='utf-8'))
    after = refresh(before)
    STATE_PATH.write_text(json.dumps(after, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Status:', after['status'], '; updated:', ', '.join(after['runResults']) or 'none')
    for err in after['errors']:
        print('WARNING:', err, file=sys.stderr)
    if not after['runResults']:
        sys.exit(1)


if __name__ == '__main__':
    main()
