"""Authoritative data adapters. Do not substitute synthetic market observations.

All dates returned in ISO-8601 format. Incoming downloads are independently validated.
Run via `python -m update.main` (GitHub Actions or locally).
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import math
import re
import zipfile
from html.parser import HTMLParser
from statistics import median
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BOE_CSV = 'https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp'
BOE_YIELDS = 'https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/latest-yield-curve-data.zip'
BOE_GUIDANCE = 'https://www.bankofengland.co.uk/monetary-policy/the-interest-rate-bank-rate'
HPI_BASE = 'https://publicdata.landregistry.gov.uk/market-trend-data/house-price-index-data'
PROPERTYDATA = 'https://api.propertydata.co.uk/prices'
STATION = (51.628884, 0.418630)
STATION_POSTCODE = 'CM12 0BP'


def fetch_bytes(url: str, *, max_bytes=12_000_000, timeout=60) -> bytes:
    req = Request(url, headers={'User-Agent': 'HouseLens/0.1 (personal UK property affordability research)', 'Accept': '*/*'})
    with urlopen(req, timeout=timeout) as r:
        if r.status != 200:
            raise ValueError(f'Unexpected HTTP status {r.status}')
        out = r.read(max_bytes + 1)
        if len(out) > max_bytes:
            raise ValueError('Response exceeded safe maximum download size')
        return out


def boe_url(codes, date_from, date_to='now'):
    return BOE_CSV + '?' + urlencode({
        'csv.x': 'yes', 'Datefrom': date_from, 'Dateto': date_to,
        'SeriesCodes': ','.join(codes), 'CSVF': 'TN', 'UsingCodes': 'Y',
        'VPD': 'Y', 'VFD': 'N',
    })


def read_boe_series(text: str, code: str):
    rows = []
    source = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    if not source.fieldnames or code not in source.fieldnames:
        raise ValueError(f'BoE series {code} is missing or malformed')
    for row in source:
        raw = (row.get(code) or '').strip()
        if raw in ('', '..', 'n/a', '-'):
            continue
        try:
            date = dt.datetime.strptime(row['DATE'].strip(), '%d %b %Y').date().isoformat()
            value = float(raw)
        except (KeyError, ValueError):
            continue
        if math.isfinite(value) and -5 <= value <= 30:
            rows.append({'date': date, 'rate': round(value, 5)})
    rows.sort(key=lambda p: p['date'])
    if not rows:
        raise ValueError(f'BoE series {code}: no valid observations')
    return rows


def get_bank_rate(fetch=fetch_bytes):
    # 1984-present; builds history entirely from BoE, not the video spreadsheet.
    url = boe_url(['IUDBEDR'], '01/Jan/1984')
    daily = read_boe_series(fetch(url).decode('utf-8-sig', errors='replace'), 'IUDBEDR')
    changes = []
    for row in daily:
        if not changes or row['rate'] != changes[-1]['rate']:
            changes.append(row)
    return {'rate': daily[-1]['rate'], 'asOf': daily[-1]['date'], 'history': changes, 'sourceUrl': url}


def get_sonia(fetch=fetch_bytes):
    now = dt.date.today()
    url = boe_url(['IUDSOIA'], (now - dt.timedelta(days=45)).strftime('%d/%b/%Y'))
    daily = read_boe_series(fetch(url).decode('utf-8-sig', errors='replace'), 'IUDSOIA')
    return {'rate': daily[-1]['rate'], 'asOf': daily[-1]['date'], 'sourceUrl': url}


def _excel_row_date(v):
    if isinstance(v, (dt.datetime, dt.date)):
        return v.date().isoformat() if isinstance(v, dt.datetime) else v.isoformat()
    if isinstance(v, (int, float)) and v > 25_000:
        return (dt.datetime(1899, 12, 30) + dt.timedelta(days=v)).date().isoformat()
    if isinstance(v, str):
        try:
            return dt.date.fromisoformat(v[:10]).isoformat()
        except ValueError:
            return None
    return None


def parse_curve_zip(content: bytes, filename_token: str, sheet_pattern: str, *, required_months=()):
    """Return (as-of date, {months: percentage-rate}) from the BoE *latest* ZIP.

    The published workbook can contain adjacent months and years headers.
    We select explicitly labelled maturity units and validate their grid.
    Observations start two rows after the maturity header.
    For required short-end tenors, use the newest sufficiently complete dated
    observation; individual tenors may be absent on the latest trading day.
    """
    from openpyxl import load_workbook
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        files = [f for f in archive.namelist()
                 if filename_token.casefold() in f.casefold()
                 and 'daily' in f.casefold()
                 and f.lower().endswith('.xlsx')]
        if not files:
            raise ValueError(f'BoE ZIP: no daily {filename_token} XLSX workbook')
        data = archive.read(files[0])
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        sheets = [n for n in wb.sheetnames if re.search(sheet_pattern, n.strip(), flags=re.I)]
        if not sheets:
            raise ValueError(f'BoE {filename_token}: requested sheet not published ({wb.sheetnames})')
        rows = list(wb[sheets[0]].iter_rows(values_only=True))
        # The BoE workbook often has TWO numerical maturity header rows:
        # "months:" (1, 2, 3, ...) and "years:" (1/12, 2/12, 3/12, ...).
        # The first numerical row is NOT necessarily denominated in years.
        # Reading months as years silently maps a 1-month rate to 12 months,
        # and loses the 3- and 6-month forecasts. Prefer an explicitly
        # labelled years header, then months, then a clearly fractional grid.
        candidates = []
        for row_idx in range(2, min(7, len(rows))):
            row = rows[row_idx]
            numeric = []
            for col_idx, value in enumerate(row[1:], 1):
                try:
                    num = float(value)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(num) and num > 0:
                    numeric.append((col_idx, num))
            if len(numeric) < 5:
                continue
            if any(a[1] > b[1] for a, b in zip(numeric, numeric[1:])):
                continue
            header = str(row[0] or '').strip().casefold()
            if 'year' in header:
                unit, priority = 'years', 3
            elif 'month' in header:
                unit, priority = 'months', 2
            elif numeric[0][1] < 0.5 and numeric[1][1] < 1:
                # Unlabelled short-end fractional years, e.g. 0.08333, 0.16667.
                unit, priority = 'years', 1
            elif numeric[0][1] >= 0.5 and numeric[0][1] <= 5 and numeric[1][1] <= 5:
                # Legacy standard curves begin at 0.5, 1.0 years.
                unit, priority = 'years', 1
            else:
                continue  # ambiguous; don't silently assign incorrect tenors
            columns_candidate = {}
            for col_idx, number in numeric:
                raw_months = number * 12 if unit == 'years' else number
                months = round(raw_months)
                if 0 < months <= 480 and abs(months - raw_months) < .15:
                    columns_candidate[col_idx] = months
            if len(columns_candidate) >= 5:
                candidates.append((priority, row_idx, columns_candidate))
        if not candidates:
            raise ValueError('BoE yield file maturity header not found or ambiguous')
        # Explicitly labelled "years:" outranks any adjacent "months:" row.
        # In equal-priority layouts the later header wins (modern row 4).
        _, mat_idx, columns = max(candidates, key=lambda x: (x[0], x[1]))
        candidates = []
        for row in rows[mat_idx + 2:]:
            date = _excel_row_date(row[0]) if row else None
            if not date:
                continue
            points = {}
            for i, months in columns.items():
                if i >= len(row):
                    continue
                try:
                    rate = float(row[i])
                except (ValueError, TypeError):
                    continue
                if math.isfinite(rate) and -5 < rate < 30:
                    points[months] = round(rate, 4)
            if points:
                candidates.append((date, points))
        if not candidates:
            raise ValueError('BoE yield file contains no dated numeric observations')
        candidates.sort(key=lambda v: v[0], reverse=True)
        if not required_months:
            return candidates[0]

        newest_date = dt.date.fromisoformat(candidates[0][0])
        # Only use curves within seven calendar days of the newest published
        # observation; otherwise the market-implied outlook is unavailable.
        # Do not silently extrapolate beyond known maturity points.
        for date, points in candidates:
            if (newest_date - dt.date.fromisoformat(date)).days > 7:
                break
            interpolated = dict(points)
            for month in required_months:
                if month in interpolated:
                    continue
                lower = max((m for m in points if m < month), default=None)
                upper = min((m for m in points if m > month), default=None)
                # A one- or two-month missing point is acceptable for this
                # indicative scenario. Wider gaps would mask poor coverage.
                if lower is None or upper is None or upper - lower > 3:
                    continue
                weight = (month - lower) / (upper - lower)
                interpolated[month] = round(points[lower] + weight * (points[upper] - points[lower]), 4)
            if all(month in interpolated for month in required_months):
                return date, interpolated
        raise ValueError('BoE OIS short-end curve has no recent complete 3, 6 and 12 month observations')
    finally:
        wb.close()


def get_market_curves(bank_rate, sonia_rate, fetch=fetch_bytes):
    """Download one official ZIP; parse OIS and inflation independently.

    Missing inflation data should not prevent a valid rate outlook, and vice versa.
    Every partial failure is recorded for display by the updater.
    """
    raw = fetch(BOE_YIELDS, max_bytes=12_000_000, timeout=120)
    results = {'warnings': []}
    try:
        ois_date, ois = parse_curve_zip(raw, 'OIS', r'fwds?,?\s*short end$', required_months=(3, 6, 12))
        basis = bank_rate - sonia_rate
        forecast = []
        for months in (3, 6, 12):
            if months in ois:
                forecast.append({'months': months,
                                 'rate': round(ois[months] + basis, 4),
                                 'oisForward': ois[months]})
        if len(forecast) != 3:
            raise ValueError('OIS curve missing one or more of 3, 6, 12 month tenors')
        results['ois'] = {'asOf': ois_date, 'forecast': forecast,
                          'soniaBasis': round(basis, 4), 'sourceUrl': BOE_YIELDS}
    except Exception as exc:
        results['warnings'].append('OIS forwards: ' + str(exc)[:160])
    try:
        inflation_date, inflation = parse_curve_zip(raw, 'GLC Inflation', r'spot curve$')
        results['gilts'] = {
            'asOf': inflation_date, 'rpiBreakeven': inflation.get(12),
            'curve': [{'months': m, 'rate': v} for m, v in sorted(inflation.items()) if m <= 60],
            'sourceUrl': BOE_YIELDS,
        }
    except Exception as exc:
        results['warnings'].append('Gilt inflation: ' + str(exc)[:160])
    if 'ois' not in results and 'gilts' not in results:
        raise ValueError('Both official curve datasets failed: ' + '; '.join(results['warnings']))
    return results


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip = 0
    def handle_starttag(self, name, attrs):
        if name in ('script', 'style', 'nav', 'footer'):
            self.skip += 1
    def handle_endtag(self, name):
        if name in ('script', 'style', 'nav', 'footer'):
            self.skip = max(0, self.skip - 1)
    def handle_data(self, value):
        if not self.skip:
            clean = ' '.join(value.split())
            if clean:
                self.text.append(clean)


def get_guidance(fetch=fetch_bytes):
    text = fetch(BOE_GUIDANCE).decode('utf-8', errors='replace')
    p = VisibleText()
    p.feed(text)
    txt = ' '.join(p.text)
    # A conservative headline extraction; never put an unverified number on-screen.
    candidates = [
        r'Inflation is expected to reach (?:about |around )?[0-9]+(?:\.[0-9]+)?% by [^.!?]{3,90}',
        r'(?:We expect|We predict) inflation to (?:rise|fall|reach) [^.!?]{5,105}',
        r'Inflation is expected to (?:rise|fall) [^.!?]{5,105}',
    ]
    match = next((m for pat in candidates if (m := re.search(pat, txt, flags=re.I))), None)
    if not match:
        raise ValueError('BoE guidance wording changed; no numeric forecast will be inferred')
    headline = match.group(0).strip()
    if len(headline) > 175:
        raise ValueError('BoE guidance extraction failed length validation')
    return {'asOf': dt.date.today().isoformat(), 'headline': headline,
            'url': BOE_GUIDANCE, 'note': 'Extracted from official BoE explanation; checked on retrieval date'}


def _shift_month(date, months):
    y = date.year + (date.month - 1 + months)//12
    m = (date.month - 1 + months)%12 + 1
    return f'{y:04d}-{m:02d}'


def parse_hpi_csv(data, source_url):
    """Official published Basildon local-authority HPI (not within-station listings)."""
    decoded = data.decode('utf-8-sig', errors='replace')
    rows = list(csv.DictReader(io.StringIO(decoded)))
    matching = []
    for r in rows:
        norm = {k.strip().lower(): v for k,v in r.items() if k}
        if norm.get('region_name', '').strip().lower() != 'basildon':
            continue
        try:
            price = float(norm.get('average_price') or norm.get('averageprice') or '')
        except ValueError:
            continue
        if price <= 0:
            continue
        date = (norm.get('date') or norm.get('month') or '').strip()[:10]
        if not re.match(r'^\d{4}-\d{2}', date):
            continue
        def num(key):
            try:
                val = float(norm.get(key, ''))
                return round(val, 3) if math.isfinite(val) else None
            except (ValueError, TypeError):
                return None
        matching.append({'date': date[:7], 'averagePrice': round(price),
                         'annualChange': num('annual_change'), 'monthlyChange': num('monthly_change')})
    if not matching:
        raise ValueError('HM Land Registry HPI: no Basildon observations in CSV')
    last = max(matching, key=lambda p: p['date'])
    return {**last, 'area': 'Basildon local authority', 'sourceUrl': source_url}


def get_hpi(fetch=fetch_bytes):
    today = dt.date.today()
    failures = []
    # UK HPI releases generally lag their observation month by ~2 months.
    for offset in range(-2, -6, -1):
        month = _shift_month(today, offset)
        url = f'{HPI_BASE}/Average-prices-{month}.csv'
        try:
            return parse_hpi_csv(fetch(url), url)
        except Exception as exc:
            failures.append(str(exc)[:120])
    raise ValueError('Land Registry HPI unavailable for the latest four candidate months: ' + ' | '.join(failures))


def miles_between(lat1, lon1, lat2, lon2):
    r = 3958.7613
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return 2*r*math.asin(min(1, math.sqrt(a)))


def classify_type(raw):
    s = re.sub(r'[\s_\-]+', ' ', str(raw or '').lower()).strip()
    if 'end of terrace' in s or 'end terrace' in s or 'end terraced' in s:
        return 'End of terrace'
    if 'semi detached' in s:
        return 'Semi-detached'
    if 'detached' in s and 'semi' not in s:
        return 'Detached'
    return None


def normalise_property(p):
    try:
        price = float(p['price'])
        bedrooms = int(p['bedrooms'])
        lat = float(p['lat'])
        lng = float(p['lng'])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(v) for v in (price, lat, lng)):
        return None
    if bedrooms < 3 or price < 450_000 or price > 600_000:
        return None
    property_type = classify_type(p.get('type') or p.get('standardised_type'))
    if not property_type:
        return None
    distance = miles_between(*STATION, lat, lng)
    if distance > 0.75:
        return None
    if p.get('sstc') is True:
        return None
    url = str(p.get('url') or '')
    if not url.startswith('https://'):
        url = None
    address = str(p.get('address') or 'Address not supplied')[:180]
    stable = f'{address.strip().lower()}|{round(lat,5)}|{round(lng,5)}'
    return {'id': hashlib.sha256(stable.encode()).hexdigest()[:18], 'address': address,
            'price': int(price), 'bedrooms': bedrooms, 'type': property_type,
            'distanceMiles': round(distance, 3), 'portal': str(p.get('portal') or 'PropertyData')[:50],
            'url': url}


def parse_propertydata(payload):
    if payload.get('status') != 'success':
        raise ValueError('PropertyData returned unsuccessful API status')
    raw = payload.get('data', {}).get('raw_data')
    if not isinstance(raw, list):
        raise ValueError('PropertyData returned no raw listings sample')
    results = {}
    for record in raw:
        if not isinstance(record, dict):
            continue
        clean = normalise_property(record)
        if clean:
            results[clean['id']] = clean
    return {'listings': sorted(results.values(), key=lambda p: (p['distanceMiles'], p['price'])),
            'sampleSize': len(raw), 'sampleLimit': 100,
            'coverageNote': 'Sample of nearby asking-price listings, not a comprehensive property-feed search; end terraces require explicit classification.'}


def get_properties(key, fetch=fetch_bytes):
    if not key:
        raise ValueError('PROPERTYDATA_API_KEY not configured')
    url = PROPERTYDATA + '?' + urlencode({'key': key, 'location': f'{STATION[0]},{STATION[1]}', 'points': 100})
    try:
        payload = json.loads(fetch(url, max_bytes=3_000_000).decode('utf-8-sig'))
    except json.JSONDecodeError as exc:
        raise ValueError('PropertyData response was not JSON') from exc
    result = parse_propertydata(payload)
    result['sourceUrl'] = 'https://propertydata.co.uk/api/documentation/prices'  # never save the API key
    return result
