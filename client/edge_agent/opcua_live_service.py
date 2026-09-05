"""Part 4 loop glue: cloud runtime config -> OPC reads -> SQLite queue -> HTTPS batch."""
import time
from .queue_store import put,batch,ok,fail,depth,prune
from .connectors.opcua_runtime import read_mapped_nodes

def enqueue_cycle(client,runtime,max_queue_rows=10000):
    points=read_mapped_nodes(client,runtime["connector_id"],runtime.get("mappings",[]),runtime.get("stale_seconds",120))
    payload={"batch_id":f"{runtime['connector_id']}-{time.time_ns()}","connector_id":runtime["connector_id"],"gateway_uid":runtime["gateway_uid"],"points":points,"read_only":True}
    key=f"opc:{runtime['connector_id']}:"+":".join(p["sequence"] for p in points)
    prune(max_queue_rows);put(payload,key);return len(points)

def upload_queued(session,cloud_url,token,batch_size=50):
    uploaded=0
    for row_id,payload_json,attempts in batch(batch_size):
        try:
            response=session.post(cloud_url.rstrip('/')+'/api/v1/edge/opc-ua/live-batch',data=payload_json,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},timeout=90)
            response.raise_for_status();ok(row_id);uploaded+=1
        except Exception as exc:fail(row_id,exc);break
    return {"uploaded_batches":uploaded,"queue_depth":depth()}
