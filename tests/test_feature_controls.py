from pathlib import Path
m=Path('app/models.py').read_text();r=Path('app/routes.py').read_text();s=Path('app/security_privacy.py').read_text()
for x in ['FleetFeatureDefaults','AssetFeatureOverride']:assert 'class '+x in m
for x in ['/fleet-feature-settings','/feature-settings','FLEET_FEATURE_DEFAULTS_CHANGED']:assert x in r
for x in ['MANDATORY_CONTROLS','PLAN_FEATURES','effective_features']:assert x in s
print('FEATURE_CONTROLS PASS')
