"""Optional free listing source: Untera's published developer API.

Never fabricates prices or geolocations. Records without a verified location
are potential matches only, NOT properties proven within 0.75 miles of station.
The API key belongs in a GitHub Actions secret; never publish it to Pages.
"""
from __future__ import annotations

import json
import math
from urllib.parse import urlencode
from urllib.request import Request, urlopen

STATION = (51.62889045, 0.418635763)
SEARCH_ENDPOINT = 'https://api.untera.io/api/v1/listings/search'


def distance_miles(lat, lng):
    lat1, lon1 = map(math.radians, STATION)
    lat2, lon2 = map(math.radians, (lat, lng))
    a = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 3958.7613 * 2 * math.asin(min(1, math.sqrt(a)))


def type_name(*values):
    text = ' '.join(str(x or '') for x in values).lower().replace('_', ' ').replace('-', ' ')
    if 'end of terrace' in text or 'end terrace' in text or 'end terraced' in text:
        return 'End of terrace'
    if 'semi detached' in text or 'semidetached' in text:
        return 'Semi-detached'
    if 'detached' in text:
        return 'Detached'
    return None


def _float(value):
    try:
        if isinstance(value, str):
            value = value.replace('£', '').replace(',', '').strip()
        v = float(value)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _coords(record):
    coords = record.get('coordinates') or record.get('geo') or {}
    place = record.get('location') if isinstance(record.get('location'), dict) else {}
    lat = _float(record.get('latitude', record.get('lat')))
    lng = _float(record.get('longitude', record.get('lng', record.get('lon'))))
    for obj in (coords if isinstance(coords,dict) else {}, place):
        if lat is None: lat = _float(obj.get('latitude', obj.get('lat')))
        if lng is None: lng = _float(obj.get('longitude', obj.get('lng', obj.get('lon'))))
    if isinstance(coords, list) and len(coords) == 2:
        # GeoJSON arrays are [longitude, latitude]. Do not guess any other order.
        lng, lat = _float(coords[0]), _float(coords[1])
    if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat,lng


def normalize_item(raw):
    if not isinstance(raw, dict): return None
    # Untera converts source prices into USD. Never convert USD back to GBP with
    # an invented FX rate; only use the original GBP-denominated asking price.
    if str(raw.get('original_currency', '')).upper() != 'GBP': return None
    price = _float(raw.get('original_price'))
    beds = _float(raw.get('bedrooms', raw.get('beds')))
    if price is None or price <= 0 or beds is None or beds < 1: return None
    address = str(raw.get('address') or raw.get('location_name') or raw.get('title') or '').strip()[:180]
    kind = type_name(raw.get('property_type'), raw.get('type'), raw.get('title'))
    if kind is None: return None
    status = ' '.join(str(raw.get(f) or '') for f in ('status','availability','transaction')).lower()
    if any(term in status for term in ('sold', 'sstc', 'under offer', 'under_offer', 'rent', 'let')):
        return None
    coord = _coords(raw)
    distance = round(distance_miles(*coord), 3) if coord else None
    if distance is not None and distance > 3.5: return None
    # If the provider has no geo-point, insist on an identifiable Billericay
    # location; never imply this proves the exact station radius.
    if distance is None and not any(term in address.casefold() for term in ('billericay','cm12')):
        return None
    safe_url = str(raw.get('url') or '')
    if not safe_url.startswith('https://'): safe_url = ''
    listing_id = str(raw.get('id') or raw.get('_id') or safe_url)
    if not listing_id: return None
    return {'id': listing_id[:160], 'price': round(price), 'bedrooms': int(beds),
            'type': kind, 'address': address or 'Address not provided',
            'distanceMiles': distance, 'distanceVerified': distance is not None,
            'url': safe_url, 'portal': 'Untera', 'sourceProvider':'Untera'}


def parse_response(payload):
    if not isinstance(payload,dict): raise ValueError('Listing response is not a JSON object')
    if payload.get('success') is False: raise ValueError('Listing provider reported an error')
    results = payload.get('results')
    if not isinstance(results,list): raise ValueError('Listing response is missing results array')
    return [p for raw in results if (p:=normalize_item(raw))]


def get_untera_listings(api_key, *, get_json=None, max_pages=8):
    if not api_key: raise ValueError('Untera key not provided')
    if get_json is None:
        def get_json(url, key):
            req=Request(url,headers={'X-API-Key':key, 'Accept':'application/json',
                          'User-Agent':'HouseLens/1.5 (personal UK home search)'})
            with urlopen(req,timeout=35) as response:
                if response.status!=200: raise ValueError('Untera request failed')
                raw=response.read(4_000_000 + 1)
                if len(raw)>4_000_000: raise ValueError('Listing response too large')
                return json.loads(raw)
    all_items=[]; seen=set(); pages=0; truncated=False
    for page in range(1,max_pages+1):
        query=urlencode({'country':'GB','location':'Billericay', 'transaction':'sale',
                         'pageSize':50,'page':page})
        payload=get_json(SEARCH_ENDPOINT+'?'+query,api_key)
        page_items=parse_response(payload)
        for p in page_items:
            if p['id'] not in seen:
                all_items.append(p); seen.add(p['id'])
        pages=page
        # Some versions use 'next_page', some use 'hasMore'; a short page can
        # also terminate pagination. Do not assume exhaustive coverage.
        raw_count=len(payload.get('results',[]))
        if payload.get('next_page') is None and payload.get('hasMore') is not True and raw_count<50:
            break
        if not raw_count: break
    else:
        truncated=True
    return {'listings':all_items,'sampleSize':len(all_items),'pages':pages,
            'coverageNote': ('Search capped at %d pages; results may be incomplete. ' % max_pages if truncated else '')+
            'Only Untera-indexed listings. Distance needs verified coordinates. ' +
            'Original GBP asking prices only; other currencies excluded.',
            'sourceUrl':'https://untera.io/developers'}


def strict_default_matches(listings):
    return [p for p in listings if 450000<=p['price']<=600000 and p['bedrooms']>=3
            and p['type'] in ('Detached','Semi-detached','End of terrace')
            and isinstance(p['distanceMiles'],(float,int)) and p['distanceMiles']<=0.75]
