"""AssetTrack 360 read-only OPC UA live runtime.

The runtime never calls set_value, call_method or alarm acknowledgement APIs.
It reads configured nodes, retains OPC timestamps/status, and returns normalized
points suitable for the durable SQLite outbound queue.
"""
from datetime import datetime, timezone
import hashlib

GOOD_STATUS = {"GOOD", "STATUSCODE(GOOD)", "0X00000000"}

def normalize_quality(status):
    text=str(status or "UNKNOWN").upper()
    if text in GOOD_STATUS or text.endswith("(GOOD)"): return "GOOD"
    if "UNCERTAIN" in text: return "UNCERTAIN"
    if "BAD" in text: return "BAD"
    return "UNKNOWN"

def iso(value):
    if not value:return datetime.now(timezone.utc).isoformat()
    if getattr(value,"tzinfo",None) is None:value=value.replace(tzinfo=timezone.utc)
    return value.isoformat()

def point_sequence(connector_id,node_id,timestamp,value):
    raw=f"{connector_id}|{node_id}|{timestamp}|{value}".encode()
    return "opc-"+hashlib.sha256(raw).hexdigest()[:48]

def read_mapped_nodes(client,connector_id,mappings,stale_seconds=120):
    now=datetime.now(timezone.utc);points=[]
    for mapping in mappings:
        node_id=mapping["source_path"];node=client.get_node(node_id);dv=node.get_data_value();value=dv.Value.Value
        source=dv.SourceTimestamp or dv.ServerTimestamp or now
        if getattr(source,"tzinfo",None) is None:source=source.replace(tzinfo=timezone.utc)
        age=max(0,(now-source).total_seconds());quality=normalize_quality(dv.StatusCode)
        if age>stale_seconds and quality=="GOOD":quality="STALE"
        if isinstance(value,bool):numeric=1.0 if value else 0.0
        elif isinstance(value,(int,float)):numeric=float(value)
        else:raise ValueError(f"unsupported_live_datatype:{type(value).__name__}")
        points.append({"source_path":node_id,"value":numeric,"quality":quality,"source_timestamp":iso(source),"server_timestamp":iso(dv.ServerTimestamp),"status_code":str(dv.StatusCode),"sequence":point_sequence(connector_id,node_id,iso(source),numeric)})
    return points
