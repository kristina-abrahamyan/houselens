"""Twice-weekly scheduled snapshot refresher. Failing source != fabricated observation."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from statistics import median
from update import feeds, local_sales, free_listings

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
    # Opt-in free provider. Fetch a broad Billericay inventory; the website
    # filters the collected stock locally, with an optional on-demand refresh.
    # Its key must be a secret and must never be included in state.json.
    key = os.environ.get('UNTERA_API_KEY', '')
    if key:
        feed = run('Untera house listings', lambda: free_listings.get_untera_listings(key))
        if feed:
            state['listings'] = feed['listings']
            state['listingsAsOf'] = timestamp
            state['listingProvider'] = 'Untera'
            state['listingCoverage'] = {'sampleSize':feed['sampleSize'],
                'note':feed['coverageNote'], 'pages':feed['pages']}
            state.setdefault('sources', {})['listings'] = feed['sourceUrl']
            # Trend snapshots contain ONLY verified properties meeting the
            # baseline criteria (not unknown locations or broad Billericay).
            matches=free_listings.strict_default_matches(feed['listings'])
            if len(matches)>=3:
                snapshot={'date':now.date().isoformat(),'observedAt':timestamp,
                          'count':len(matches),'medianPrice':int(median(p['price'] for p in matches)),
                          'scope':'verified station radius, default filters',
                          'properties':[{'id':p['id'],'price':p['price']} for p in matches]}
                old=[s for s in state.get('snapshots',[]) if s.get('date')!=snapshot['date']]
                state['snapshots']=(old+[snapshot])[-350:]
    else:
        state.setdefault('sources', {})['listings'] = 'Not configured: free UNTERA_API_KEY GitHub secret'
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
