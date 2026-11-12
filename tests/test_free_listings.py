"""Tests for Untera adapter; only offline fake responses, never API calls."""
import unittest
from update import free_listings

STATION = {'latitude': 51.62889045, 'longitude': 0.418635763}

def house(**changes):
    item = {'id': 'listing-1', 'title': '3 bed semi-detached house Billericay',
            'property_type': 'semi-detached', 'original_currency': 'GBP',
            'original_price': 525000, 'bedrooms': 3, 'address': 'Billericay CM12',
            'url': 'https://example.com/home', **STATION}
    return {**item, **changes}

class FreeListingsTests(unittest.TestCase):
    def test_station_coordinates_and_exact_budget_match(self):
        p=free_listings.normalize_item(house())
        self.assertAlmostEqual(p['distanceMiles'],0,places=2)
        self.assertEqual(free_listings.strict_default_matches([p]),[p])

    def test_falls_outside_or_lacks_coords(self):
        self.assertIsNone(free_listings.normalize_item(house(latitude=51.68)))
        p=free_listings.normalize_item(house(latitude=None,longitude=None))
        self.assertIsNotNone(p)
        self.assertIsNone(p['distanceMiles'])
        self.assertEqual(free_listings.strict_default_matches([p]),[])

    def test_ignored_unknown_or_wrong_currency(self):
        self.assertIsNone(free_listings.normalize_item(house(original_currency='USD',price_usd=700000)))
        self.assertEqual(free_listings.normalize_item(house(property_type='terraced', title='Terraced house'))['type'],'Type unverified')
        self.assertIsNone(free_listings.normalize_item(house(status='Sold STC')))
        self.assertEqual(free_listings.normalize_item(house(original_price='£525,000'))['price'],525000)

    def test_explicit_end_terrace(self):
        p=free_listings.normalize_item(house(property_type='terraced',title='3 bedroom end of terrace house'))
        self.assertEqual(p['type'],'End of terrace')

    def test_unknown_house_type_is_review_only_not_verified(self):
        p=free_listings.normalize_item(house(property_type='residential',title='3 bedroom house for sale'))
        self.assertEqual(p['type'],'Type unverified')
        self.assertEqual(free_listings.strict_default_matches([p]), [])
        self.assertIsNone(free_listings.normalize_item(house(property_type='flat',title='3 bedroom flat')))
        self.assertIsNone(free_listings.normalize_item(house(property_type='mid-terrace',title='3 bed mid terrace home')))

    def test_diagnostic_counts_do_not_include_addresses_or_secrets(self):
        diag={'rawResults':0,'reasons':{}}
        items=free_listings.parse_response({'results':[
            house(),house(id='two',property_type='residential',title='3 bedroom house'),
            house(id='three',property_type='flat',title='3 bedroom flat'),
            house(id='four',original_currency='USD')]},diag)
        self.assertEqual(len(items),2)
        self.assertEqual(diag['rawResults'],4)
        self.assertEqual(diag['reasons']['unconfirmedType'],1)
        self.assertEqual(diag['reasons']['otherType'],1)
        self.assertEqual(diag['reasons']['currency'],1)
        self.assertNotIn('Billericay',str(diag))

    def test_pagination_mock_and_duplicate(self):
        def fake(url,key):
            self.assertEqual(key,'unt_test_not_secret')
            self.assertIn('country=GB',url)
            return {'results':[house(),house(id='listing-2')]}
        output=free_listings.get_untera_listings('unt_test_not_secret',get_json=fake)
        self.assertEqual(output['sampleSize'],2)
        self.assertEqual(output['pages'],1)
        self.assertEqual(output['diagnostics']['rawResults'],2)

    def test_provider_errors_do_not_become_empty_results(self):
        with self.assertRaises(ValueError):
            free_listings.parse_response({'error':'not authorised'})

if __name__=='__main__': unittest.main()
