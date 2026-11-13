import datetime as dt
import os
import unittest
from unittest.mock import patch
from update import ons_cpi
from update.main import refresh
from test_listing_refresh_status import StubFeeds, NOW

CSV = '''Title,CPI ANNUAL RATE 00: ALL ITEMS 2015=100
CDID,D7G7
Release Date,21-10-2026
1989,5.2
2026 Q3,3.7
2026 JUL,3.6
2026 AUG,3.6
2026 SEP,3.5
2026 OCT,9.9
'''

class InflationAutomationTests(unittest.TestCase):
    def test_latest_observed_inflation_is_monthly_and_not_future(self):
        result = ons_cpi.parse_ons_cpi_csv(CSV, today=dt.date(2026, 11, 13))
        self.assertEqual(result['annualRate'], 3.5)  # October cannot be released during October
        self.assertEqual(result['asOf'], '2026-09-01')
        self.assertEqual(result['published'], '2026-10-21')
        result = ons_cpi.parse_ons_cpi_csv(CSV, today=dt.date(2026, 9, 30))
        self.assertEqual(result['annualRate'], 3.5)
        self.assertEqual(result['asOf'], '2026-09-01')

    def test_reject_stale_ons_instead_of_faking_observation(self):
        with self.assertRaisesRegex(ValueError, 'too old'):
            ons_cpi.parse_ons_cpi_csv(CSV, today=dt.date(2027, 3, 15))

    def test_every_six_hour_refresh_does_not_burn_listing_credits(self):
        old={'sources': {}, 'listingProvider': 'RealtyAPI (unofficial Rightmove API)',
             'listings': [{'id': 'existing', 'price': 500000}],
             'listingsAsOf':'2026-11-12T00:00:00Z',
             'listingRefresh': {'status':'ok', 'attemptedAt': '2026-11-12T00:00:00Z'}}
        with patch.dict(os.environ, {'REALTYAPI_KEY':'secret'}), patch(
                'update.main.realty_listings.get_realty_listings', side_effect=AssertionError('Should not call')):
            output=refresh(old, now=NOW, adapters=StubFeeds, refresh_listings=False)
        self.assertEqual(output['listings'][0]['id'], 'existing')
        self.assertEqual(output['listingRefresh']['status'], 'ok')

    def test_new_reports_discovered_across_2028_and_no_fixed_2026_csv(self):
        from update import cpi_projections
        from test_cpi_projections import SAMPLE
        from urllib.error import HTTPError
        def fetch(url, **kwargs):
            if url.endswith('/2028/february-2028'):
                return SAMPLE.replace('2026-11-05', '2028-02-05').replace('2026 Q4','2028 Q4')
            raise HTTPError(url,404,'Not found',{},None)
        res=cpi_projections.get_cpi_projection(fetch,today=dt.date(2028,2,10))
        self.assertEqual(res['asOf'],'2028-02-05')

if __name__=='__main__': unittest.main()
