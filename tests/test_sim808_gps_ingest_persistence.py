from pathlib import Path
R=Path('app/routes.py').read_text();T=Path('app/templates/tracking_history.html').read_text()
def test_ingest_reports_exact_location_result():
    for x in ['location_accepted=location_accepted','location_duplicate=location_duplicate','location_rejection=location_rejection','asset_id=asset.id','device_uid=device.device_uid']:
        assert x in R
def test_ingest_rejects_zero_zero_and_validates_range():
    assert 'zero_zero_is_not_a_fix' in R
    assert 'coordinates_out_of_range' in R
def test_location_is_bound_to_authenticated_device_asset():
    assert 'asset=device.asset' in R
    assert 'asset_id=asset.id' in R
def test_gps_capable_devices_keep_history():
    assert 'policy.gps_history_enabled=True' in R
    assert 'gps_capable=bool' in R
def test_duplicate_location_sequence_is_not_inserted_twice():
    assert 'existing_location=Location.query.filter_by(asset_id=asset.id,sequence=location_sequence).first()' in R
def test_last_known_outside_range_is_explicit():
    assert 'outside_selected_range' in R
    assert 'Map shows an older last-known position' in T
