"""Windows-only OPC DA read-only bridge.

Uses COM automation locally. The public surface intentionally exposes only
server enumeration, browse and synchronous read. No write, method, alarm
acknowledgement or control API exists.
"""
import hashlib, os, platform
from datetime import datetime, timezone

QUALITY={192:'GOOD',216:'GOOD',0:'BAD',4:'BAD',8:'BAD',24:'BAD',64:'UNCERTAIN'}

def windows_preflight():
    is_windows=os.name=='nt'
    result={'windows':is_windows,'architecture':platform.architecture()[0],'python':platform.python_version(),'com_available':False,'openopc_available':False,'read_only':True}
    if is_windows:
        try:
            import win32com.client  # noqa
            result['com_available']=True
        except ImportError: pass
        try:
            import OpenOPC  # noqa
            result['openopc_available']=True
        except ImportError: pass
    result['ready']=is_windows and (result['openopc_available'] or result['com_available'])
    return result

def _client():
    if os.name!='nt': raise RuntimeError('opc_classic_requires_windows')
    try:
        import OpenOPC
        return OpenOPC.client()
    except ImportError as exc: raise RuntimeError('OpenOPC_or_compatible_COM_bridge_required') from exc

def list_servers(host='localhost'):
    opc=_client()
    try:return [{'progid':str(x),'host':host} for x in opc.servers(host)]
    finally:
        try:opc.close()
        except Exception:pass

def browse(server_progid,host='localhost',branch='*',flat=True,max_items=1000):
    opc=_client();limit=max(1,min(1000,int(max_items)))
    try:
        opc.connect(server_progid,host);items=opc.list(branch=branch,flat=bool(flat)) or []
        return [{'item_id':str(x),'name':str(x).split('.')[-1]} for x in items[:limit]]
    finally:
        try:opc.close()
        except Exception:pass

def _quality(value):
    text=str(value or '').upper()
    if 'GOOD' in text:return 'GOOD'
    if 'UNCERTAIN' in text:return 'UNCERTAIN'
    if 'BAD' in text:return 'BAD'
    try:return QUALITY.get(int(value),'UNKNOWN')
    except Exception:return 'UNKNOWN'

def read_items(server_progid,item_ids,host='localhost',timeout_seconds=10):
    if not item_ids or len(item_ids)>500:raise ValueError('item_count_must_be_1_to_500')
    opc=_client()
    try:
        opc.connect(server_progid,host);raw=opc.read(list(item_ids),timeout=max(1000,min(120000,int(timeout_seconds)*1000)))
        rows=[]
        for item,result in zip(item_ids,raw):
            if isinstance(result,(tuple,list)):
                value=result[0] if len(result)>0 else None;quality=result[1] if len(result)>1 else 'UNKNOWN';stamp=result[2] if len(result)>2 else None
            else:value,quality,stamp=result,'UNKNOWN',None
            rows.append({'item_id':item,'value':value,'quality':_quality(quality),'source_timestamp':stamp.isoformat() if hasattr(stamp,'isoformat') else str(stamp or datetime.now(timezone.utc).isoformat())})
        return rows
    finally:
        try:opc.close()
        except Exception:pass

def rows_to_points(rows,mappings):
    by_id={x['item_id']:x for x in rows};points=[]
    for m in mappings:
        row=by_id.get(m['item_id'])
        if not row:continue
        try:value=float(row['value'])
        except (TypeError,ValueError):continue
        stamp=row['source_timestamp'];seq='opcda:'+hashlib.sha256(f"{m['mapping_id']}:{stamp}:{value}".encode()).hexdigest()[:48]
        points.append({'source_path':m['source_path'],'value':value,'quality':row['quality'],'source_timestamp':stamp,'sequence':seq})
    return points

# Deliberately no write(), set(), execute(), alarm_ack() or control function.
