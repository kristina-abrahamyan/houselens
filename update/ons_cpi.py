"""Official observed UK CPI annual inflation, independent of BoE CPI forecasts.

ONS MM23 D7G7 (monthly annual % change), downloaded from the ONS series
CSV generator. Missing/revised observations never become guessed numbers.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import re

SOURCE_PAGE = 'https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7g7/mm23'
CSV_URL = ('https://www.ons.gov.uk/generator?format=csv&uri='
           '%2Feconomy%2Finflationandpriceindices%2Ftimeseries%2Fd7g7%2Fmm23')
MONTHS = {name: i for i, name in enumerate(('JAN','FEB','MAR','APR','MAY','JUN',
                                             'JUL','AUG','SEP','OCT','NOV','DEC'), 1)}


def parse_ons_cpi_csv(raw, *, today=None):
    today = today or dt.date.today()
    text = raw.decode('utf-8-sig', errors='replace') if isinstance(raw, bytes) else raw
    rows = csv.reader(io.StringIO(text))
    observations = {}
    release_date = None
    for row in rows:
        if len(row) < 2:
            continue
        label, value = row[0].strip().strip('"'), row[1].strip().strip('"')
        if label.casefold() in ('release date', 'release date:'):
            for fmt in ('%d-%m-%Y', '%d %B %Y', '%Y-%m-%d'):
                try:
                    release_date = dt.datetime.strptime(value, fmt).date()
                    break
                except ValueError:
                    pass
        match = re.fullmatch(r'(20\d\d)\s+([A-Za-z]{3})', label)
        if not match:
            continue  # skip annual and quarterly observations
        month = MONTHS.get(match.group(2).upper())
        if not month:
            continue
        try:
            d = dt.date(int(match.group(1)), month, 1)
            rate = float(value)
        except ValueError:
            continue
        # Monthly CPI for a given month is normally first released the next month.
        # Reject observations claiming a month not yet complete at publication.
        if d <= today and (not release_date or (d.year, d.month) < (release_date.year, release_date.month)) and -10 <= rate <= 30:
            observations[d] = rate
    if not observations:
        raise ValueError('ONS CPI D7G7 CSV contained no valid monthly inflation observations')
    date = max(observations)
    if date < today - dt.timedelta(days=100):
        raise ValueError('ONS CPI D7G7 latest monthly observation is too old')
    return {'asOf': date.isoformat(), 'annualRate': observations[date],
            'published': release_date.isoformat() if release_date and release_date <= today else None,
            'series': [{'month': d.isoformat(), 'rate': observations[d]}
                       for d in sorted(observations)[-36:]],
            'sourceUrl': SOURCE_PAGE,
            'measure': 'ONS actual monthly headline CPI annual inflation (D7G7)'}


def get_ons_cpi(fetch, *, today=None):
    return parse_ons_cpi_csv(fetch(CSV_URL, max_bytes=1_500_000), today=today)
