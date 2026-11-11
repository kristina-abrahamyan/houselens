"""CM12 property *completed sale* comparables from HM Land Registry Price Paid Data.

No dependency on Housemetric; its Billericay charts were used to identify useful
methodology only. Official yearly CSVs are used directly under the OGL.

No coordinates, bedrooms or floor area are present in PPD, so these statistics
must NEVER be labelled as matching the station radius or a 3-bedroom filter.
Do not merge them into the live asking-property listings list.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
from statistics import median
from urllib.request import Request, urlopen

BASE = 'https://price-paid-data.publicdata.landregistry.gov.uk'
SOURCE = 'https://www.gov.uk/government/statistical-data-sets/price-paid-data-yearly-file'
ATTRIBUTION = ('Contains HM Land Registry data © Crown copyright and database right 2021. '
               'This data is licensed under the Open Government Licence v3.0.')
MAX_RECORDS = 5000  # fail visibly rather than silently sample a large subset


def source_url(year):
    if not isinstance(year, int) or not 1995 <= year <= dt.date.today().year + 1:
        raise ValueError('Invalid PPD annual year')
    return f'{BASE}/pp-{year}.csv'


def parse_ppd_rows(rows, year):
    """Read PPD's 16-position no-header format; exclude nonstandard transfers.

    Published annual files are revised and include delayed registrations. Only
    anonymised transaction features are retained in GitHub's public JSON.
    """
    out = {}
    for row in rows:
        if len(row) < 15:
            continue
        uid = str(row[0]).strip().strip('{}')
        postcode = str(row[3]).strip().upper()
        if not postcode.startswith('CM12 '):
            continue
        ptype = str(row[4]).strip().upper()
        if ptype not in {'D', 'S', 'T'}:
            continue
        if str(row[14]).strip().upper() != 'A':
            continue  # single standard residential sales only
        try:
            value = int(float(row[1]))
            date = dt.date.fromisoformat(str(row[2])[:10])
        except (TypeError, ValueError, OverflowError):
            continue
        if date.year != year or not (100_000 <= value <= 3_000_000):
            continue
        # Annual full files incorporate corrections; record status is only
        # applicable to monthly change-only releases.
        if not uid or uid in out:
            continue
        # HMLR does NOT distinguish middle from end of terrace; T is NOT
        # considered one of the user's qualifying property types.
        sector = 'CM12 0' if postcode.startswith('CM12 0') else ('CM12 9' if postcode.startswith('CM12 9') else 'CM12 other')
        out[uid] = {'id': uid, 'date': date.isoformat(), 'price': value,
                    'type': ptype, 'sector': sector}
        if len(out) > MAX_RECORDS:
            raise ValueError('Unexpectedly high CM12 record volume; not silently truncating')
    return sorted(out.values(), key=lambda r: (r['date'], r['id']))


def fetch_year(year, opener=urlopen):
    """Stream official national CSV; avoid downloading 100+ MB into RAM."""
    url = source_url(year)
    request = Request(url, headers={'User-Agent': 'HouseLens/1.3 (noncommercial local property research)',
                                    'Accept': 'text/csv,*/*'})
    with opener(request, timeout=180) as response:
        if getattr(response, 'status', 200) != 200:
            raise ValueError(f'Price Paid Data year {year}: HTTP {response.status}')
        # The yearly files are large; streaming keeps Actions memory bounded.
        reader = csv.reader(io.TextIOWrapper(response, encoding='utf-8-sig', newline=''))
        return parse_ppd_rows(reader, year)


def month_index(s):
    d = dt.date.fromisoformat(s)
    return d.year * 12 + d.month


def summarise(records, today):
    """Compare the same six calendar months year-on-year, not two changing mixes
    of weekly listings. Exclude newest ~4 months due to registration delays.
    """
    anchor = (today - dt.timedelta(days=120)).replace(day=1)
    end_exclusive = month_index(anchor.isoformat())
    min_recent, max_recent = end_exclusive - 6, end_exclusive
    min_previous, max_previous = min_recent - 12, max_recent - 12

    def subgroup(sector):
        def allowed(r):
            if r['type'] not in {'D', 'S'}:
                return False  # end-of-terrace cannot be identified from PPD
            return sector == 'CM12' or r['sector'] == sector
        recent = [r for r in records if allowed(r) and min_recent <= month_index(r['date']) < max_recent]
        prior = [r for r in records if allowed(r) and min_previous <= month_index(r['date']) < max_previous]
        return recent, prior

    # CM12 0 is a sector, not a 0.75-mile station-radius geometry.
    recent, prior = subgroup('CM12 0')
    scope = 'CM12 0 postcode sector'
    minimum = 12
    if len(recent) < minimum or len(prior) < minimum:
        recent, prior = subgroup('CM12')
        scope, minimum = 'CM12 postcode district', 20
    if len(recent) < minimum or len(prior) < minimum:
        raise ValueError('Not enough published detached/semi-detached sales for meaningful local comparison')
    new_mid = median(r['price'] for r in recent)
    old_mid = median(r['price'] for r in prior)
    if old_mid <= 0:
        raise ValueError('Bad preceding house-price median')
    change = (new_mid / old_mid - 1) * 100
    # Protect against implausibly large composition shifts in the sample.
    if not (-35 < change < 35):
        raise ValueError('Local sold-price change exceeds quality threshold')
    end = (anchor - dt.timedelta(days=1)).strftime('%Y-%m')
    prior_end = (anchor.replace(year=anchor.year-1) - dt.timedelta(days=1)).strftime('%Y-%m')
    band = sum(450_000 <= r['price'] <= 600_000 for r in recent)
    return {'asOf': today.isoformat(), 'periodEnd': end, 'previousPeriodEnd': prior_end,
            'scope': scope, 'typeDescription': 'Detached and semi-detached completed sales',
            'medianPrice': round(new_mid), 'previousMedianPrice': round(old_mid),
            'annualChange': round(change, 3), 'count': len(recent), 'previousCount': len(prior),
            'bandSales': band, 'priceBand': '£450,000–£600,000', 'sourceUrl': SOURCE,
            'note': 'Price Paid Data has no bedroom count, floor area, station distance or end-terrace flag; not a listing search. Latest months excluded for registration lag.',
            'attribution': ATTRIBUTION}


def required_years(today):
    """Years covering BOTH six-month comparable periods at the 120-day lag.

    For example January 2027 still needs 2025 transactions, even though the
    current calendar year is 2027. Never reset the analysis at New Year.
    """
    anchor = (today - dt.timedelta(days=120)).replace(day=1)
    latest_year = (anchor - dt.timedelta(days=1)).year
    first_recent = month_index(anchor.isoformat()) - 6
    first_previous = first_recent - 12
    first_year = (first_previous - 1) // 12
    return tuple(range(first_year, latest_year + 1))


def update_local_sales(existing=None, *, today=None, fetcher=fetch_year):
    """Maintain a fully independent official sold-price dataset into 2027+.

    Download the needed annual CSVs once on first deployment, re-check the
    current year each refresh, and refresh earlier required years after the
    27th (monthly official corrections / late registrations).
    """
    today = today or dt.date.today()
    monthly_key = today.strftime('%Y-%m')
    existing = existing or {}
    by_year = dict(existing.get('byYear') or {})
    checked = dict(existing.get('checkedMonths') or {})
    needed = required_years(today)
    for year in needed:
        key = str(year)
        current = year == today.year
        needs = key not in by_year or (current and today.day >= 1 and checked.get(key) != monthly_key) or (
            not current and today.day >= 27 and checked.get(key) != monthly_key)
        if needs:
            # Only replace a year's previous published record set after its
            # complete national CSV has been successfully parsed.
            by_year[key] = fetcher(year)
            checked[key] = monthly_key
    by_year = {str(year): by_year[str(year)] for year in needed}
    checked = {str(year): checked.get(str(year)) for year in needed}
    records = [row for rows in by_year.values() for row in rows]
    summary = summarise(records, today)
    return {'dataset': {'byYear': by_year, 'checkedMonths': checked},
            'summary': summary}
