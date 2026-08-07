import json, math, os, time, urllib.parse, urllib.request
_CACHE={}
def _json_get(url,timeout=12):
    req=urllib.request.Request(url,headers={'User-Agent':'AssetTrack360/1.0 (+https://fleettrack.wykiesautomation.co.za)','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as response:return json.loads(response.read().decode('utf-8'))
def haversine_m(a,b):
    lat1,lon1,lat2,lon2=map(math.radians,(a[0],a[1],b[0],b[1]));dlat=lat2-lat1;dlon=lon2-lon1
    value=math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 12742017.6*math.asin(math.sqrt(value))
def route_quality(rows):
    if not rows:return {'grade':'POOR','average_accuracy':None,'gaps':0,'suspect_jumps':0,'accepted':0,'total':0}
    accuracies=[float(row.accuracy_m or 0) for row in rows if row.accuracy_m is not None];gaps=jumps=0;accepted=1
    for previous,current in zip(rows,rows[1:]):
        elapsed=max(1,(current.sampled_at-previous.sampled_at).total_seconds());distance=haversine_m((previous.latitude,previous.longitude),(current.latitude,current.longitude))
        if elapsed>300:gaps+=1
        if distance>max(250,elapsed/3600*220000+100):jumps+=1
        else:accepted+=1
    average=round(sum(accuracies)/len(accuracies)) if accuracies else None
    score=100-(average or 35)-gaps*8-jumps*18;grade='GOOD' if score>=65 else 'FAIR' if score>=35 else 'POOR'
    return {'grade':grade,'average_accuracy':average,'gaps':gaps,'suspect_jumps':jumps,'accepted':accepted,'total':len(rows)}
def match_route(rows):
    base=os.getenv('OSRM_BASE_URL','').rstrip('/')
    if not base:return {'status':'raw_only','reason':'provider_not_configured','segments':[],'confidence':0}
    usable=rows[-100:]
    if len(usable)<2:return {'status':'raw_only','reason':'not_enough_points','segments':[],'confidence':0}
    coords=';'.join(f'{row.longitude:.6f},{row.latitude:.6f}' for row in usable)
    timestamps=';'.join(str(int(row.sampled_at.timestamp())) for row in usable)
    radiuses=';'.join(str(int(max(10,min(80,float(row.accuracy_m or 25))))) for row in usable)
    query=urllib.parse.urlencode({'overview':'full','geometries':'geojson','steps':'false','gaps':'split','tidy':'true','timestamps':timestamps,'radiuses':radiuses})
    try:data=_json_get(f'{base}/match/v1/driving/{coords}?{query}')
    except Exception:return {'status':'raw_only','reason':'provider_unavailable','segments':[],'confidence':0}
    if data.get('code')!='Ok':return {'status':'raw_only','reason':data.get('code','match_failed'),'segments':[],'confidence':0}
    segments=[];confidence=0
    for item in data.get('matchings',[]):
        geometry=(item.get('geometry') or {}).get('coordinates') or [];confidence=max(confidence,float(item.get('confidence') or 0))
        if len(geometry)>1:segments.append([[lat,lon] for lon,lat in geometry])
    return {'status':'matched' if segments else 'raw_only','reason':None if segments else 'no_geometry','segments':segments,'confidence':confidence,'raw_point_count':len(usable)}
def _first(address,*fields):
    for field in fields:
        value=address.get(field)
        if value:return str(value).strip()
    return None

def reverse_geocode(lat,lon,accuracy_m=None,force_refresh=False):
    base=os.getenv('GEOCODING_BASE_URL','https://nominatim.openstreetmap.org').rstrip('/')
    key=f'{round(float(lat),4)},{round(float(lon),4)}';now=time.time();cached=_CACHE.get(key)
    if cached and not force_refresh and now-cached[0]<86400:return cached[1]
    query=urllib.parse.urlencode({'lat':lat,'lon':lon,'format':'jsonv2','addressdetails':1,'zoom':18,'accept-language':'en'})
    try:data=_json_get(f'{base}/reverse?{query}')
    except Exception as exc:return {'status':'unavailable','possible_address':None,'reason':'provider_unavailable','detail':str(exc)[:120]}
    address=data.get('address') or {};accuracy=float(accuracy_m or 0)
    number=_first(address,'house_number');road=_first(address,'road','pedestrian','footway','path','residential')
    area=_first(address,'suburb','neighbourhood','quarter','city_district');city=_first(address,'city','town','village','municipality')
    province=_first(address,'state','province');postcode=_first(address,'postcode');country=_first(address,'country')
    street=' '.join(x for x in (number,road) if x)
    precision='possible_street_address' if accuracy and accuracy<=25 else 'possible_street_or_area' if accuracy and accuracy<=100 else 'approximate_area' if accuracy>100 else 'possible_address'
    if accuracy>25 and road:street=road
    lines=[]
    if street:lines.append(street)
    locality=', '.join(x for x in (area,city) if x and x not in lines)
    if locality:lines.append(locality)
    region=', '.join(x for x in (province,postcode) if x)
    if region:lines.append(region)
    if country:lines.append(country)
    possible=', '.join(lines) or data.get('display_name')
    result={'status':'ok' if possible else 'unavailable','possible_address':possible,'address_lines':lines,'house_number':number if accuracy<=25 or not accuracy else None,'road':road,'area':area,'city':city,'state':province,'postcode':postcode,'country':country,'precision':precision,'accuracy_m':accuracy_m,'source':'OpenStreetMap Nominatim' if 'nominatim.openstreetmap.org' in base else 'Configured geocoding provider'}
    _CACHE[key]=(now,result);return result
