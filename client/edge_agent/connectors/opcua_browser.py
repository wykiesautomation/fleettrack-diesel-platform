"""Read-only OPC UA browse/read executor used by the local Edge Gateway."""
def browse_nodes(client, root_node='i=85', max_depth=2, max_nodes=250):
    max_depth=max(1,min(int(max_depth),5));max_nodes=max(25,min(int(max_nodes),1000));out=[]
    def walk(node,depth):
        if depth>max_depth or len(out)>=max_nodes:return
        for child in node.get_children():
            if len(out)>=max_nodes:return
            try:
                node_id=child.nodeid.to_string();display=child.get_display_name().Text;browse=child.get_browse_name().Name;node_class=str(child.get_node_class()).split('.')[-1]
                try:data_type=child.get_data_type_as_variant_type().name
                except Exception:data_type=''
                try:children=child.get_children();has_children=bool(children)
                except Exception:has_children=False
                out.append({'node_id':node_id,'display_name':display,'browse_name':browse,'node_class':node_class,'data_type':data_type,'access_level':'READ_ONLY','has_children':has_children})
                if has_children:walk(child,depth+1)
            except Exception:continue
    walk(client.get_node(root_node),0);return out

def read_node(client,node_id):
    node=client.get_node(node_id);dv=node.get_data_value();value=dv.Value.Value
    return {'display_name':node.get_display_name().Text,'data_type':node.get_data_type_as_variant_type().name,'value':value,'quality':str(dv.StatusCode),'status_code':str(dv.StatusCode),'source_timestamp':dv.SourceTimestamp.isoformat() if dv.SourceTimestamp else '','server_timestamp':dv.ServerTimestamp.isoformat() if dv.ServerTimestamp else ''}
