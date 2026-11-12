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
    if 'endterrace' in text: return 'End of terrace'
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


# Aggregate rejection reasons; never write raw provider responses or API keys to state.
REASON_LABELS = {
    'invalid': 'Invalid provider record', 'currency': 'No original GBP asking price',
    'price': 'No usable asking price', 'bedrooms': 'Bedrooms not specified',
    'status': 'Not clearly available for sale',
    'otherType': 'Definitely not an allowed house type',
    'outside': 'Outside the broad Billericay station area',
    'location': 'Billericay location cannot be established',
    'id': 'Missing listing identifier', 'unconfirmedType': 'Property type not confirmed',
}


def normalize_detailed(raw):
    if not isinstance(raw, dict): return None, 'invalid'
    if str(raw.get('original_currency', '')).upper() != 'GBP': return None, 'currency'
    price = _float(raw.get('original_price'))
    beds = _float(raw.get('bedrooms', raw.get('beds')))
    if price is None or price <= 0: return None, 'price'
    if beds is None or beds < 1: return None, 'bedrooms'
    status = ' '.join(str(raw.get(f) or '') for f in ('status','availability','transaction')).lower()
    if any(term in status for term in ('sold', 'sstc', 'under offer', 'under_offer', 'rent', 'let')):
        return None, 'status'
    coord = _coords(raw)
    distance = round(distance_miles(*coord), 3) if coord else None
    if distance is not None and distance > 3.5: return None, 'outside'
    address = str(raw.get('address') or raw.get('location_name') or (raw.get('location') if isinstance(raw.get('location'),str) else '') or raw.get('city') or raw.get('title') or '').strip()[:180]
    if distance is None and not any(term in address.casefold() for term in ('billericay','cm12')):
        return None, 'location'
    kind = type_name(raw.get('property_type'), raw.get('type'), raw.get('title'))
    if kind is None:
        text=' '.join(str(raw.get(k) or '') for k in ('property_type','type','title')).lower()
        import re
        if re.search(r'\b(flat|apartment|maisonette|studio|bungalow|land|plot|commercial)\b|\bmid[ -]?terrace\b',text):
            return None, 'otherType'
    safe_url = str(raw.get('url') or '')
    if not safe_url.startswith('https://'): safe_url = ''
    listing_id = str(raw.get('id') or raw.get('_id') or safe_url)
    if not listing_id: return None, 'id'
    item = {'id': listing_id[:160], 'price': round(price), 'bedrooms': int(beds),
            'type': kind or 'Type unverified', 'address': address or 'Address not provided',
            'distanceMiles': distance, 'distanceVerified': distance is not None,
            'url': safe_url, 'portal': 'Untera', 'sourceProvider':'Untera'}
    return item, ('unconfirmedType' if kind is None else None)


def normalize_item(raw):
    return normalize_detailed(raw)[0]


def parse_response(payload, diagnostics=None):
    if not isinstance(payload,dict): raise ValueError('Listing response is not a JSON object')
    if payload.get('success') is False: raise ValueError('Listing provider reported an error')
    results = payload.get('results')
    if not isinstance(results,list): raise ValueError('Listing response is missing results array')
    out=[]
    for raw in results:
        item, reason=normalize_detailed(raw)
        if diagnostics is not None:
            diagnostics['rawResults']+=1
            if reason:
                counts=diagnostics['reasons']
                counts[reason]=counts.get(reason,0)+1
        if item: out.append(item)
    return out


def get_untera_listings(api_key, *, get_json=None, max_pages=8):
    if not api_key: raise ValueError('Untera key not provided')
    if get_json is None:
        def get_json(url, key):
            req=Request(url,headers={'X-API-Key':key, 'Accept':'application/json',
                          'User-Agent':'HouseLens/1.6 (personal UK home search)'})
            with urlopen(req,timeout=35) as response:
                if response.status!=200: raise ValueError('Untera request failed')
                raw=response.read(4_000_000 + 1)
                if len(raw)>4_000_000: raise ValueError('Listing response too large')
                return json.loads(raw)
    all_items=[]; seen=set(); pages=0; truncated=False
    diagnostics={'rawResults':0,'reasons':{}}
    for page in range(1,max_pages+1):
        query=urlencode({'country':'GB','location':'Billericay', 'transaction':'sale',
                         'pageSize':50,'page':page})
        payload=get_json(SEARCH_ENDPOINT+'?'+query,api_key)
        page_items=parse_response(payload,diagnostics)
        for item in page_items:
            if item['id'] not in seen:
                all_items.append(item);seen.add(item['id'])
        pages=page
        raw_count=len(payload.get('results',[]))
        if payload.get('next_page') is None and payload.get('hasMore') is not True and raw_count<50:
            break
        if not raw_count: break
    else:
        truncated=True
    return {'listings':all_items,'sampleSize':len(all_items),'pages':pages,
            'diagnostics':diagnostics,
            'coverageNote': ('Search capped at %d pages; results may be incomplete. ' % max_pages if truncated else '')+
            'Only Untera-indexed listings. Distance needs verified coordinates. ' +
            'Original GBP asking prices only; other currencies excluded.',
            'sourceUrl':'https://untera.io/developers'}


def strict_default_matches(listings):
    return [p for p in listings if 450000<=p['price']<=600000 and p['bedrooms']>=3
            and p['type'] in ('Detached','Semi-detached','End of terrace')
            and isinstance(p['distanceMiles'],(float,int)) and p['distanceMiles']<=0.75]
