import importlib.util
spec=importlib.util.spec_from_file_location("ri","app/route_intelligence.py");m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert round(m.haversine_m((-26.73624,27.84615),(-26.73624,27.84615)))==0
assert m.reverse_geocode(-26.7,27.8)["status"] in ("unavailable","ok")
print("ROUTE_INTELLIGENCE PASS")
