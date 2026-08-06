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
def _split_route(rows,gap_seconds=300):
    segments=[];current=[];suspect=0
    for row in rows:
        if not current:
            current=[row];continue
        previous=current[-1];elapsed=max(1,(row.sampled_at-previous.sampled_at).total_seconds())
        distance=haversine_m((previous.latitude,previous.longitude),(row.latitude,row.longitude))
        impossible=distance>max(250,elapsed/3600*220000+100)
        if elapsed>gap_seconds:
            if len(current)>=2:segments.append(current)
            current=[row]
        elif impossible:
            suspect+=1
        else:current.append(row)
    if len(current)>=2:segments.append(current)
    return segments,suspect

def _chunks(rows,size=35,overlap=3):
    if len(rows)<=size:return [rows]
    result=[];step=max(2,size-overlap)
    for index in range(0,len(rows)-1,step):
        part=rows[index:index+size]
        if len(part)>=2:result.append(part)
        if index+size>=len(rows):break
    return result

def _match_chunk(base,rows):
    coords=';'.join(f'{row.longitude:.6f},{row.latitude:.6f}' for row in rows)
    timestamps=';'.join(str(int(row.sampled_at.timestamp())) for row in rows)
    radiuses=';'.join(str(int(max(10,min(80,float(row.accuracy_m or 25))))) for row in rows)
    query=urllib.parse.urlencode({'overview':'full','geometries':'geojson','steps':'false','gaps':'split','tidy':'true','timestamps':timestamps,'radiuses':radiuses})
    data=_json_get(f'{base}/match/v1/driving/{coords}?{query}',timeout=15)
    if data.get('code')!='Ok':return None,0,data.get('code','match_failed')
    geometries=[];confidence=0
    for item in data.get('matchings',[]):
        geometry=(item.get('geometry') or {}).get('coordinates') or [];confidence=max(confidence,float(item.get('confidence') or 0))
        if len(geometry)>1:geometries.append([[lat,lon] for lon,lat in geometry])
    return geometries,confidence,None

def match_route(rows):
    base=os.getenv('OSRM_BASE_URL','').rstrip('/')
    if not base:return {'status':'raw_only','reason':'provider_not_configured','segments':[],'raw_segments':[],'confidence':0}
    usable=rows[-200:]
    source_segments,suspect=_split_route(usable)
    if not source_segments:return {'status':'raw_only','reason':'not_enough_points','segments':[],'raw_segments':[],'confidence':0}
    matched=[];raw=[];confidences=[];requests=failures=0
    for source in source_segments:
        for chunk in _chunks(source,35,3):
            requests+=1
            try:geometries,confidence,error=_match_chunk(base,chunk)
            except Exception:geometries=[];confidence=0;error='provider_unavailable'
            if geometries:
                matched.extend(geometries);confidences.append(confidence)
            else:
                failures+=1;raw.append([[row.latitude,row.longitude] for row in chunk])
    status='matched' if matched and not raw else 'partial' if matched else 'raw_only'
    reason=None if matched else 'provider_unavailable'
    denominator=len(matched)+len(raw);coverage=round(len(matched)/denominator,3) if denominator else 0
    return {'status':status,'reason':reason,'segments':matched,'raw_segments':raw,'confidence':round(sum(confidences)/len(confidences),3) if confidences else 0,'coverage':coverage,'requests':requests,'failed_requests':failures,'source_segments':len(source_segments),'suspect_jumps_removed':suspect,'raw_point_count':len(usable)}

def reverse_geocode(lat,lon):
    base=os.getenv('GEOCODING_BASE_URL','').rstrip('/')
    if not base:return {'status':'unavailable','possible_address':None,'reason':'provider_not_configured'}
    key=f'{round(float(lat),4)},{round(float(lon),4)}';now=time.time();cached=_CACHE.get(key)
    if cached and now-cached[0]<86400:return cached[1]
    query=urllib.parse.urlencode({'lat':lat,'lon':lon,'format':'jsonv2','addressdetails':1,'zoom':18})
    try:data=_json_get(f'{base}/reverse?{query}')
    except Exception:return {'status':'unavailable','possible_address':None,'reason':'provider_unavailable'}
    address=data.get('address') or {};parts=[]
    for field in ('road','suburb','city','town','municipality','state','country'):
        value=address.get(field)
        if value and value not in parts:parts.append(value)
    result={'status':'ok','possible_address':', '.join(parts) or data.get('display_name'),'road':address.get('road'),'area':address.get('suburb'),'city':address.get('city') or address.get('town'),'state':address.get('state'),'country':address.get('country'),'source':'Configured geocoding provider'}
    _CACHE[key]=(now,result);return result
