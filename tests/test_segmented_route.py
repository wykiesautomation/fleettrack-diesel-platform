import importlib.util
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
spec=importlib.util.spec_from_file_location("ri","app/route_intelligence.py");ri=importlib.util.module_from_spec(spec);spec.loader.exec_module(ri)
t=datetime.now(timezone.utc)
rows=[SimpleNamespace(latitude=-26.7,longitude=27.8+i*0.0001,accuracy_m=12,sampled_at=t+timedelta(seconds=i*10)) for i in range(80)]
chunks=ri._chunks(rows,35,3);assert len(chunks)==3 and all(2<=len(x)<=35 for x in chunks)
segments,suspect=ri._split_route(rows);assert len(segments)==1 and suspect==0
print("SEGMENTED_ROUTE PASS")
