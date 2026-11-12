"""Optional RealtyAPI (unofficial Rightmove) property search.

Only normalized, non-secret listings enter the public static snapshot. The
provider's UK GBP search is checked again locally against the actual station.
Unverified terrace subtype or location is never silently called a match.
"""
from __future__ import annotations

import json
import math
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

STATION = (51.62889045, 0.418635763)  # same reference used throughout HouseLens
SEARCH_ENDPOINT = 'https://rightmove.realtyapi.io/search/bycoordinates'
REASON_LABELS = {
    'invalid': 'Malformed provider record', 'currency': 'Non-GBP price',
    'price': 'Asking price not available', 'bedrooms': 'Bedrooms not specified',
    'status': 'Not available for sale', 'otherType': 'Excluded property type',
    'outside': 'Outside 3 miles of Billericay station',
    'id': 'Missing listing identifier', 'unconfirmedType': 'Type needs verification',
    'location': 'Location not verified',
}


def _number(value):
    if isinstance(value, bool): return None
    if isinstance(value, dict):
        for k in ('amount', 'value', 'price', 'numeric', 'current'):
            if k in value: return _number(value[k])
        return None
    try:
        if isinstance(value, str):
            # Price strings may say 'Guide Price £550,000', or '£550,000'.
            m = re.search(r'([0-9][0-9,]*(?:\.[0-9]+)?)', value)
            if not m: return None
            value = m.group(1).replace(',', '')
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def _coords(raw):
    for obj in (raw.get('location'), raw.get('coordinates'), raw.get('geo'), raw.get('geolocation'), raw.get('map'), raw):
        if isinstance(obj, dict):
            lat = _number(obj.get('latitude', obj.get('lat')))
            lon = _number(obj.get('longitude', obj.get('lng', obj.get('lon'))))
            if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
                return (lat, lon)
        if isinstance(obj, (list, tuple)) and len(obj) == 2:
            # GeoJSON coordinate arrays are longitude, latitude.
            lon, lat = _number(obj[0]), _number(obj[1])
            if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
                return (lat, lon)
    return None


def distance_miles(lat, lon):
    x, y = map(math.radians, STATION)
    a, b = math.radians(lat), math.radians(lon)
    z = math.sin((a-x)/2)**2+math.cos(x)*math.cos(a)*math.sin((b-y)/2)**2
    return 3958.7613*2*math.asin(min(1, math.sqrt(max(0,z))))


def _kind(*values):
    txt = ' '.join(str(x or '') for x in values).lower().replace('_',' ').replace('-',' ')
    if re.search(r'\bend\s*(?:of\s*)?terrac(?:e|ed)\b|\bendterrace\b|\bterrac(?:e|ed)\s+end\b',txt): return 'End of terrace'
    if re.search(r'\bsemi\s*detached\b',txt): return 'Semi-detached'
    if re.search(r'\bdetached\b',txt): return 'Detached'
    return None


def normalize_detailed(raw):
    if not isinstance(raw,dict): return None,'invalid'
    price_field=raw.get('price')
    currency = str(raw.get('currency') or (price_field.get('currency') if isinstance(price_field,dict) else None) or 'GBP').upper()
    if currency not in ('GBP', '£'): return None,'currency'
    # The provider documents GBP numeric prices, but may include a displayPrice.
    # An explicit foreign currency is never interpreted as GBP.
    price = _number(raw.get('priceAmount', raw.get('askingPrice', price_field)))
    if price is None and isinstance(raw.get('displayPrices'), list) and raw['displayPrices']:
        price = _number(raw['displayPrices'][0].get('displayPrice') if isinstance(raw['displayPrices'][0], dict) else raw['displayPrices'][0])
    beds = _number(raw.get('bedrooms',raw.get('beds',raw.get('bedroomCount'))))
    if price is None or price <= 0: return None,'price'
    if beds is None or beds < 1: return None,'bedrooms'
    status=' '.join(str(raw.get(k) or '') for k in ('status','availability','listingStatus','statusText')).lower()
    if re.search(r'\bsold\b|\bsstc\b|under[ -]?offer|\brent(?:al)?\b|\blet\b|withdrawn',status): return None,'status'
    coordinate=_coords(raw)
    distance=round(distance_miles(*coordinate),3) if coordinate else None
    if distance is not None and distance>3.05: return None,'outside'
    type_fields=(raw.get('propertySubType'), raw.get('propertyType'),raw.get('property_type'),raw.get('type'),raw.get('summary'),raw.get('title'))
    kind=_kind(*type_fields)
    if re.search(r'\b(flat|apartment|maisonette|studio|bungalow|park\s*home|commercial|land|plot|mid\s*terrace|mid\s*terraced)\b', ' '.join(str(x or '') for x in type_fields).lower().replace('-',' ')):
        return None,'otherType'
    item_id=str(raw.get('id') or raw.get('propertyId') or '').strip()
    if not re.fullmatch(r'\d{3,20}',item_id): return None,'id'
    addr=raw.get('displayAddress') or raw.get('address') or raw.get('display_address') or raw.get('title') or 'Address not provided'
    if isinstance(addr, dict): addr=', '.join(str(v) for v in addr.values() if isinstance(v,(str,int)))
    address=str(addr)[:180]
    # Make a safe direct original-listing link; never embed provider input as JS.
    link='https://www.rightmove.co.uk/properties/'+item_id
    return {'id':'rightmove:'+item_id,'price':round(price),'bedrooms':int(beds),
            'type':kind or 'Type unverified','address':address,
            'distanceMiles':distance,'distanceVerified':distance is not None,
            'url':link,'portal':'Rightmove via RealtyAPI','sourceProvider':'RealtyAPI'},('unconfirmedType' if kind is None else ('location' if distance is None else None))


def normalize_item(raw): return normalize_detailed(raw)[0]


def _items(payload):
    if not isinstance(payload,dict): raise ValueError('Response is not a JSON object')
    if payload.get('success') is False or payload.get('error'): raise ValueError('Provider returned an error')
    inner=payload.get('data') if isinstance(payload.get('data'),dict) else payload
    results=inner.get('properties')
    if results is None: results=inner.get('results')
    if results is None: results=inner.get('listings')
    if results is None and isinstance(payload.get('data'), list): results=payload['data']
    if not isinstance(results,list): raise ValueError('Missing properties/results array in response')
    return results, inner


def build_search_params(page=1, *,min_price=300000,max_price=1000000,min_beds=2,radius=3):
    return {'latitude':STATION[0], 'longitude':STATION[1], 'radius':radius,
            'page':page, 'resultCount':40, 'sortOrder':'distance',
            'searchType':'BUY', 'propertyType':'house,detached,semi_detached,terraced',
            'priceRange':f'min:{int(min_price)},max:{int(max_price)}',
            'bedroomsRange':f'min:{int(min_beds)}'}


def get_realty_listings(api_key, *, get_json=None, max_pages=4):
    if not api_key or not str(api_key).strip(): raise ValueError('RealtyAPI key not provided')
    if not (1 <= max_pages <= 10): raise ValueError('Invalid page limit')
    if get_json is None:
        def get_json(url,key):
            req=Request(url,headers={'x-realtyapi-key':key, 'Accept':'application/json','User-Agent':'HouseLens/1.7'})
            with urlopen(req,timeout=40) as response:
                if response.status!=200: raise ValueError('RealtyAPI HTTP error')
                body=response.read(4_000_001)
                if len(body)>4_000_000: raise ValueError('Listing payload exceeds size limit')
                return json.loads(body)
    all_items=[];seen=set();diagnostics={'rawResults':0,'reasons':{}};pages=0;truncated=False
    for page in range(1,max_pages+1):
        url=SEARCH_ENDPOINT+'?'+urlencode(build_search_params(page))
        payload=get_json(url,api_key)
        raw,meta=_items(payload)
        diagnostics['rawResults']+=len(raw)
        for record in raw:
            item,reason=normalize_detailed(record)
            if reason: diagnostics['reasons'][reason]=diagnostics['reasons'].get(reason,0)+1
            if item and item['id'] not in seen:
                all_items.append(item);seen.add(item['id'])
        pages=page
        next_page=meta.get('nextPage', payload.get('nextPage'))
        if next_page is None and isinstance(meta.get('pagination'),dict):
            next_page=meta['pagination'].get('nextPage')
        has_next = next_page is True or (isinstance(next_page, int) and not isinstance(next_page,bool) and next_page>page)
        if not raw or not has_next:
            break
        if page==max_pages:truncated=True
    return {'listings':all_items,'sampleSize':len(all_items),'pages':pages,
            'diagnostics':diagnostics,'truncated':truncated,
            'coverageNote':('Search was capped at %d pages. '%max_pages if truncated else '')+
              'Unofficial third-party Rightmove feed; coverage and ongoing reuse permissions are unverified. '+
              'Saved search scope: £300k–£1m, at least 2 bedrooms, within 3 miles of the station. '+
              'Changing filters outside this scope requires a broader server refresh.',
            'sourceUrl':'https://www.realtyapi.io/api/rightmove/searchbycoordinates'}


def strict_default_matches(listings):
    return [p for p in listings if 450000<=p['price']<=600000 and p['bedrooms']>=3
            and p['type'] in ('Detached','Semi-detached','End of terrace')
            and isinstance(p['distanceMiles'],(float,int)) and p['distanceMiles']<=0.75]
