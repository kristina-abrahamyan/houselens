"""Independent Bank of England Monetary Policy Report CPI forecast importer.

Uses published *central projection* four-quarter CPI rates, not RPI gilt
breakevens or scraped/invented data. New report month URLs are probed from the
current date, so the app does not depend on a 2026 spreadsheet or a hard-coded
2026 report. Failed validation is a visible data-source warning.
"""
from __future__ import annotations

import datetime as dt
import re
from html.parser import HTMLParser
from urllib.error import HTTPError

MPR_ROOT = 'https://www.bankofengland.co.uk/monetary-policy-report'
MONTHS = ('january','february','march','april','may','june','july','august',
          'september','october','november','december')


class TablesAndText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.current = None
        self.row = None
        self.cell = None
        self.depth = 0
        self.visible = []
        self.metadata_dates = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self.skip += 1
        if tag == 'meta':
            if attrs.get('property') in ('article:published_time','datePublished') or attrs.get('name') in ('date','publish-date','datePublished'):
                self.metadata_dates.append(attrs.get('content', ''))
        if tag == 'time' and attrs.get('datetime'):
            self.metadata_dates.append(attrs['datetime'])
        if tag == 'table':
            if self.depth == 0:
                self.current = []
            self.depth += 1
        elif self.depth == 1 and tag == 'tr':
            self.row = []
        elif self.depth == 1 and tag in ('th', 'td'):
            self.cell = []

    def handle_data(self, data):
        if self.skip == 0:
            self.visible.append(data)
        if self.depth and self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self.skip = max(0, self.skip - 1)
        if self.depth == 1 and tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(' '.join(self.cell).split()))
            self.cell = None
        elif self.depth == 1 and tag == 'tr' and self.row is not None:
            if self.row:
                self.current.append(self.row)
            self.row = None
        elif tag == 'table' and self.depth:
            self.depth -= 1
            if self.depth == 0 and self.current is not None:
                self.tables.append(self.current)
                self.current = None


def _publication_date(doc):
    # Prefer machine-readable source dates; only use an explicit visible
    # publication date when metadata is absent. Never label retrieval day as
    # the date of the report itself.
    for candidate in doc.metadata_dates:
        m = re.search(r'(20\d{2}-\d\d-\d\d)', candidate)
        if m:
            try:
                return dt.date.fromisoformat(m.group(1)).isoformat()
            except ValueError:
                pass
    text = ' '.join(' '.join(doc.visible).split())
    m = re.search(r'Published on\s+(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})', text, re.I)
    if m:
        try:
            return dt.datetime.strptime(' '.join(m.groups()), '%d %B %Y').date().isoformat()
        except ValueError:
            pass
    raise ValueError('BoE report publication date was not found')


def _reported_peak(doc, published):
    """Optional BoE narrative peak; never infer a mid-year peak from Q4 data."""
    visible = ' '.join(' '.join(doc.visible).split())
    pattern = (r'(?:expected|projected)\s+to\s+(?:rise|reach|peak)(?:\s+to)?\s+'
               r'(?:around|about|approximately)\s+(\d{1,2}(?:\.\d+)?)\s*%\s+'
               r'(?:by|in|around)\s+(?:the\s+)?(middle|mid|end|start)\s+of\s+'
               r'(next year|20\d{2})')
    for match in re.finditer(pattern, visible, flags=re.I):
        # Limit to explicit inflation context; exclude unrelated forecasts.
        previous = visible[max(0, match.start()-240):match.start()].lower()
        if 'inflation' not in previous:
            continue
        rate = float(match.group(1))
        if not 0 <= rate <= 20:
            continue
        year = int(published[:4])+1 if match.group(3).casefold() == 'next year' else int(match.group(3))
        if not int(published[:4]) <= year <= int(published[:4])+3:
            continue
        term = match.group(2).casefold()
        label = 'mid' if term in ('middle', 'mid') else ('early' if term == 'start' else 'late')
        return {'rate': rate, 'period': f'{label}-{year}',
                'description': f'around {rate:g}% {label}-{year}',
                'basis': 'BoE published narrative, approximate, not a quarterly data point'}
    return None


def parse_cpi_report(payload, source_url):
    """Extract year-end quarterly, four-quarter CPI rates from Table 3.B.

    The numbers in parentheses are prior-report comparisons; only the first
    percentage in each central projection cell is read. Other tables and the
    adverse/weak-demand scenario sections must not be used instead.
    """
    if isinstance(payload, bytes):
        payload = payload.decode('utf-8', errors='replace')
    doc = TablesAndText()
    doc.feed(payload)
    published = _publication_date(doc)
    for table in doc.tables:
        headers = None
        for row in table:
            quarters = [re.search(r'\b(20\d{2})\s*Q([1-4])\b', cell, re.I) for cell in row]
            if sum(m is not None for m in quarters) >= 2:
                headers = [m.group(0).replace(' ', ' ') if m else None for m in quarters]
                break
        if not headers:
            continue
        in_central = False
        for row in table:
            first = row[0].casefold().strip() if row else ''
            if 'central projection' in first:
                in_central = True
                continue
            if 'adverse inflation' in first or 'weaker demand' in first:
                in_central = False
            if not in_central or not re.search(r'\bcpi\s+inflation\b', first):
                continue
            points = []
            # The first header can be blank, corresponding to the row label.
            for i, label in enumerate(headers):
                if not label or i >= len(row):
                    continue
                m = re.match(r'^\s*(-?\d+(?:\.\d+)?)\b', row[i])
                if not m:
                    continue
                value = float(m.group(1))
                if -3 <= value <= 20:
                    points.append({'quarter': label.upper().replace('  ', ' '), 'rate': value})
            if len(points) < 2:
                raise ValueError('BoE central CPI projection has fewer than two usable quarters')
            points.sort(key=lambda p: p['quarter'])
            # Report cannot claim projection dates before it was published.
            if max(p['quarter'][:4] for p in points) < published[:4]:
                raise ValueError('BoE CPI forecast dates predate the report')
            return {
                'peakGuidance': _reported_peak(doc, published),
                'asOf': published,
                'sourceUrl': source_url,
                'series': points,
                'measure': 'four-quarter CPI inflation, central projection',
                'note': 'Quarter-end annual CPI inflation forecasts; not a precise CPI path for each intervening month.'
            }
    raise ValueError('Official BoE report no longer contains an identifiable central CPI projection table')


def _month_offset(day, back):
    index = day.year * 12 + day.month - 1 - back
    year, month_idx = divmod(index, 12)
    return year, month_idx


def get_cpi_projection(fetch, *, today=None, max_months=8):
    """Find the newest readable BoE report from the past ~8 months.

    No unauthorised service or credentials are needed. Latest report data
    remain valid until a new quarterly publication becomes available; reports
    older than 160 days are not considered current in the UI.
    """
    today = today or dt.date.today()
    errors = []
    for back in range(max_months):
        year, idx = _month_offset(today, back)
        url = f'{MPR_ROOT}/{year}/{MONTHS[idx]}-{year}'
        try:
            result = parse_cpi_report(fetch(url, max_bytes=9_000_000), url)
            release = dt.date.fromisoformat(result['asOf'])
            if release > today or (today - release).days > 160:
                raise ValueError('BoE report is not a current release')
            return result
        except (HTTPError, ValueError, UnicodeError) as ex:
            errors.append(type(ex).__name__)
    raise ValueError('No validated recent official BoE CPI projection found in latest report months')
