import unittest
from urllib.parse import urlparse, parse_qs
from update import realty_listings as R

STATION = {'latitude': R.STATION[0], 'longitude': R.STATION[1]}

def house(**updates):
    obj = {'id': 1234567, 'price': 525000, 'bedrooms': 3,
           'propertyType': 'semi_detached', 'displayAddress': 'Billericay CM12',
           'location': STATION}
    obj.update(updates)
    return obj

class RealtyTests(unittest.TestCase):
    def test_query_is_geographically_targeted(self):
        q=R.build_search_params()
        self.assertEqual(q['latitude'],R.STATION[0]); self.assertEqual(q['longitude'],R.STATION[1]); self.assertEqual(q['radius'],3)
        self.assertEqual(q['searchType'],'BUY'); self.assertIn('min:300000',q['priceRange']); self.assertEqual(q['bedroomsRange'],'min:2')

    def test_strict_station_radius_budget_type(self):
        p=R.normalize_item(house())
        self.assertEqual(p['distanceMiles'],0)
        self.assertEqual(R.strict_default_matches([p]),[p])
        self.assertEqual(R.strict_default_matches([R.normalize_item(house(price=700000))]),[])
        self.assertEqual(R.strict_default_matches([R.normalize_item(house(location={'latitude':51.67,'longitude':0.41}))]),[])

    def test_ambiguous_type_and_location_unverified(self):
        p, reason=R.normalize_detailed(house(propertyType='terraced'))
        self.assertEqual(reason,'unconfirmedType'); self.assertEqual(p['type'],'Type unverified')
        self.assertEqual(R.strict_default_matches([p]),[])
        p,reason=R.normalize_detailed(house(location=None))
        self.assertEqual(reason,'location'); self.assertIsNone(p['distanceMiles'])
        self.assertEqual(R.strict_default_matches([p]),[])
        p,reason=R.normalize_detailed(house(propertyType='end_of_terrace'))
        self.assertIsNone(reason); self.assertEqual(p['type'],'End of terrace')

    def test_rejects_unavailable_or_flats(self):
        self.assertEqual(R.normalize_detailed(house(status='Sold STC'))[1],'status')
        self.assertEqual(R.normalize_detailed(house(propertyType='flat'))[1],'otherType')
        self.assertEqual(R.normalize_detailed(house(currency='USD'))[1],'currency')

    def test_pagination_dedupe_no_private_key_in_result(self):
        pages=[]
        def fake(url,key):
            self.assertEqual(key,'test_key_only'); pages.append(parse_qs(urlparse(url).query)['page'][0])
            if len(pages)==1:return {'properties':[house(),house(id=7654321)],'nextPage':True}
            return {'properties':[house(),house(id=8888888,propertyType='terraced')],'nextPage':False}
        result=R.get_realty_listings('test_key_only',get_json=fake)
        self.assertEqual(pages,['1','2']); self.assertEqual(result['sampleSize'],3)
        self.assertEqual(result['diagnostics']['rawResults'],4)
        self.assertNotIn('test_key_only',str(result))

    def test_failed_provider_is_an_error(self):
        with self.assertRaises(ValueError):R.get_realty_listings('key',get_json=lambda *a:{'error':'invalid'})

if __name__=='__main__':unittest.main()
