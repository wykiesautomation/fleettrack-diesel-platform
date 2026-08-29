# AssetTrack 360 Local Edge Gateway Agent

Production-candidate, read-only OPC UA agent for a Windows plant PC or VM.

## Setup

```powershell
python -m pip install -r client/local_edge_gateway/requirements.txt
python -m client.local_edge_gateway.cli bootstrap --cloud https://assettrack360.wykiesautomation.co.za --gateway-uid EDGE-SITE01-01
python -m client.local_edge_gateway.cli run
```

The gateway token is shown once in **Edge Gateways** and is stored in the local user profile. Store OPC usernames/passwords or certificate paths in `secrets.json` under the configured local secret reference. The cloud never receives the plain OPC password.

## Safety

The agent exposes Browse and Read only. There is no write, method-call, setpoint, alarm acknowledgement or PLC control implementation.
