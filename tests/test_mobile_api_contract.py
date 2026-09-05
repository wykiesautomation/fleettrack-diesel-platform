def test_mobile_contract_routes_present():
    text=open("app/routes.py",encoding="utf-8").read()
    for route in ["/api/v1/mobile/register","/api/v1/mobile/location","/api/v1/mobile/location/batch","/api/v1/mobile/heartbeat","/api/v1/mobile/config","/api/v1/mobile/tracking/start","/api/v1/mobile/tracking/stop","/api/v1/mobile/status"]:
        assert route in text

def test_platforms_present():
    text=open("app/routes.py",encoding="utf-8").read()
    for platform in ["web","android","ios"]: assert platform in text
