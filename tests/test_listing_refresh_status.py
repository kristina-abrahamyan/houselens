"""Ensure the live snapshot never reports the previous Untera feed as RealtyAPI."""
import datetime as dt
import os
import unittest
from unittest.mock import patch
from update.main import refresh

NOW = dt.datetime(2026, 11, 12, 2, 0, tzinfo=dt.timezone.utc)

class StubFeeds:
    @staticmethod
    def get_bank_rate():
        return {'rate': 4.0, 'asOf': '2026-11-10', 'history': [], 'sourceUrl': 'https://bankofengland.co.uk'}
    @staticmethod
    def get_sonia():
        return {'rate': 4.0, 'asOf': '2026-11-10'}
    @staticmethod
    def get_market_curves(*_):
        return {'warnings': []}
    @staticmethod
    def get_guidance():
        return None
    @staticmethod
    def get_hpi():
        return None

OLD = {
    'listings': [{'id':'untera_1','price':500000}],
    'listingsAsOf': '2026-11-12T01:00:00Z',
    'listingProvider': 'Untera',
    'listingCoverage': {'sampleSize': 400, 'diagnostics': {'rawResults': 400}},
    'sources': {'listings': 'https://untera.io/developers'},
    'snapshots': [],
    'errors': [],
}

class RefreshStateTests(unittest.TestCase):
    def test_no_key_removes_untera_and_says_missing_key(self):
        with patch.dict(os.environ, {'REALTYAPI_KEY': ''}):
            after = refresh(OLD, now=NOW, adapters=StubFeeds)
        self.assertEqual(after['listingRefresh']['status'], 'missing_key')
        self.assertEqual(after['listings'], [])
        self.assertIsNone(after['listingsAsOf'])
        self.assertEqual(after['listingCoverage']['diagnostics']['rawResults'], 0)
        self.assertNotIn('untera', str(after).lower())

    def test_failed_api_removes_untera_and_reports_failure(self):
        with patch.dict(os.environ, {'REALTYAPI_KEY':'private-secret'}), patch(
                'update.main.realty_listings.get_realty_listings', side_effect=ValueError('rate limit')):
            after=refresh(OLD,now=NOW,adapters=StubFeeds)
        self.assertEqual(after['listingRefresh']['status'],'failed')
        self.assertEqual(after['listings'], [])
        self.assertIsNone(after['listingsAsOf'])
        self.assertIn('RealtyAPI listings:', ' '.join(after['errors']))
        self.assertNotIn('private-secret', str(after))

    def test_success_has_observation_and_new_diagnostics(self):
        feed={'listings': [],'sampleSize': 0,'pages': 1,'truncated': False,
              'diagnostics': {'rawResults':3, 'reasons': {'price':3}},
              'coverageNote': 'Limited sample.', 'sourceUrl':'https://www.realtyapi.io/api/rightmove/searchbycoordinates'}
        with patch.dict(os.environ,{'REALTYAPI_KEY':'private-secret'}), patch(
                'update.main.realty_listings.get_realty_listings', return_value=feed):
            after=refresh(OLD,now=NOW,adapters=StubFeeds)
        self.assertEqual(after['listingRefresh']['status'],'empty')
        self.assertEqual(after['listingRefresh']['rawRecords'], 3)
        self.assertEqual(after['listingCoverage']['diagnostics']['rawResults'],3)
        self.assertIn('2026-11-12T02:00',after['listingsAsOf'])
        self.assertEqual(after['listingProvider'], 'RealtyAPI (unofficial Rightmove API)')
        self.assertNotIn('private-secret', str(after))

if __name__=='__main__': unittest.main()
