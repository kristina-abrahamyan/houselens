"""Twice-weekly scheduled snapshot refresher. Failing source != fabricated observation."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from statistics import median
from update import feeds

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
    key = os.environ.get('PROPERTYDATA_API_KEY', '')
    if key:
        feed = run('PropertyData listings', lambda: adapters.get_properties(key))
        if feed:
            state['listings'] = feed['listings']
            state['listingsAsOf'] = timestamp
            state['listingCoverage'] = {'sampleSize': feed['sampleSize'], 'note': feed['coverageNote']}
            state['sources']['listings'] = feed['sourceUrl']
            listings = feed['listings']
            # Permanent dated historical observations permitted by provider licensing.
            # Never present them as current property availability.
            if listings:
                snapshot = {'date': now.date().isoformat(), 'observedAt': timestamp,
                            'count': len(listings), 'medianPrice': int(median(p['price'] for p in listings)),
                            'properties': [{'id':p['id'], 'price':p['price']} for p in listings]}
                old = [s for s in state.get('snapshots', []) if s.get('date') != snapshot['date']]
                state['snapshots'] = (old + [snapshot])[-350:]
    else:
        state['sources']['listings'] = 'Not configured: add GitHub secret PROPERTYDATA_API_KEY'
    # Prevent a provider outage from making a 60+ day-old listing appear active.
    if state.get('listingsAsOf'):
        try:
            age = (now - dt.datetime.fromisoformat(state['listingsAsOf'].replace('Z', '+00:00'))).days
            if age >= 60:
                state['listings'] = []
                errs.append('PropertyData listings expired after 60-day provider caching limit')
        except (TypeError, ValueError):
            state['listings'] = []
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
