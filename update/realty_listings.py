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
    price = _number(raw.get('priceAmount', raw.get('askingPrice', raw.get('numericPrice', raw.get('priceValue', price_field)))))
    if price is None:
        price = _number(raw.get('displayPrice', raw.get('displayedPrice')))
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


# Only follow known response-envelope field names. Do NOT recursively search arbitrary
# lists: that could silently turn error/audit records into supposed properties.
RESULT_KEYS = ('properties', 'results', 'listings', 'items', 'propertyList', 'searchResults')
WRAPPER_KEYS = ('data', 'result', 'results', 'response', 'body', 'payload', 'searchResults', 'searchResult', 'content', 'listings', 'propertyList')


def _shape_keys(obj):
    """Safe schema diagnostics: field *names*, never values or API credentials."""
    if isinstance(obj, dict):
        return ','.join(sorted(str(k)[:36] for k in obj.keys())[:16]) or '(none)'
    return type(obj).__name__


def _provider_error(payload):
    """Detect provider errors even when a proxy responds with HTTP 200 JSON."""
    if not isinstance(payload, dict):
        return None
    status = payload.get('statusCode', payload.get('status'))
    code = payload.get('code')
    if payload.get('success') is False or payload.get('ok') is False:
        return 'provider indicated success=false'
    if isinstance(status, int) and status >= 400:
        return f'provider HTTP status {status}'
    if isinstance(code, int) and code >= 400:
        return f'provider error code {code}'
    if payload.get('error') not in (None, False, '', {}):
        return 'provider error field present'
    # APIs sometimes respond 200 with {message: 'Invalid API key'} etc.
    # Classify such messages but NEVER print the supplied message itself.
    info = str(payload.get('message') or payload.get('detail') or '').lower()
    if any(marker in info for marker in ('unauthoriz','invalid api key','invalid key','missing api key','forbidden')):
        return 'provider rejected the API credential'
    if any(marker in info for marker in ('insufficient credit','quota exceeded','rate limit','payment required','limit reached')):
        return 'provider quota or credit limit reached'
    return None


def _items(payload):
    """Accept published search-list envelopes; fail explicitly on unknown shapes.

    RealtyAPI does not currently publish a machine-readable response schema for
    this endpoint, so do not assert one undocumented JSON wrapper. All candidate
    containers must hold a list, and lists are accepted only at known keys.
    """
    if isinstance(payload, list):
        return payload, {}
    if not isinstance(payload, dict):
        raise ValueError(f'Unexpected RealtyAPI JSON root type: {type(payload).__name__}')
    err = _provider_error(payload)
    if err:
        raise ValueError('RealtyAPI response error: ' + err)

    seen = set()
    queue = [(payload, 0)]
    # Track metadata on the way down for response pagination (e.g. root nextPage
    # while property array is nested under data.results).
    collected_meta = {}
    observed = []
    while queue:
        node, depth = queue.pop(0)
        if not isinstance(node, dict) or id(node) in seen or depth > 5:
            continue
        seen.add(id(node))
        observed.append(_shape_keys(node))
        err = _provider_error(node)
        if err:
            raise ValueError('RealtyAPI response error: ' + err)
        for key in ('nextPage', 'pagination', 'pageInfo', 'hasNextPage', 'totalPages', 'page'):
            if key in node and key not in collected_meta:
                collected_meta[key] = node[key]
        for key in RESULT_KEYS:
            candidate = node.get(key)
            if isinstance(candidate, list):
                return candidate, collected_meta
        # Some APIs use data: [...] or result: [...], rather than
        # data: {properties: [...]}. These keys are still explicit allow-lists.
        for key in ('data', 'result', 'response', 'payload'):
            if isinstance(node.get(key), list):
                return node[key], collected_meta
        for key in WRAPPER_KEYS:
            candidate = node.get(key)
            if isinstance(candidate, dict):
                queue.append((candidate, depth + 1))
    # This log is useful even for a 200 response with an undocumented envelope.
    # No listing addresses, values, headers, passwords or keys are logged.
    path_shapes = ' / '.join(observed[:4])
    raise ValueError('Unrecognized RealtyAPI response format; JSON field names: ' + path_shapes[:350])


def _has_next(meta, page, raw_count):
    next_page = meta.get('nextPage')
    if next_page is not None:
        if isinstance(next_page, bool):
            return next_page
        if isinstance(next_page, (int, float)):
            return next_page > page
        if isinstance(next_page, str):
            return next_page.lower() in ('true', 'yes') or (next_page.isdigit() and int(next_page)>page)
    page_info = meta.get('pagination') or meta.get('pageInfo')
    if isinstance(page_info, dict):
        if page_info.get('hasNextPage') is not None:
            return bool(page_info['hasNextPage'])
        target = page_info.get('nextPage')
        if isinstance(target, bool): return target
        if isinstance(target, (int,float)): return target>page
        total = page_info.get('totalPages') or page_info.get('pages')
        if isinstance(total, (int,float)): return page < total
    if meta.get('hasNextPage') is not None:
        return bool(meta['hasNextPage'])
    total = meta.get('totalPages')
    if isinstance(total, (int,float)):
        return page < total
    # Missing pagination metadata means exactly one page, not an assumed next.
    return False

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
        if not raw or not _has_next(meta, page, len(raw)):
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
