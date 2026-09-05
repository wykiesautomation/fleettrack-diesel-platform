from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8')

def batch_block():
    return R[R.index('def mobile_tracker_location_batch():'):R.index('def mobile_tracking_start():')]

def test_batch_accepts_authenticated_batch_or_point_identity():
    b=batch_block()
    assert "batch_device_id=str(data.get('device_id') or '').strip().upper()" in b
    assert "item.get('device_id') or batch_device_id or device.device_uid" in b
    assert "batch_device_id and batch_device_id!=device.device_uid.upper()" in b

def test_batch_accepts_current_and_legacy_gps_field_names():
    b=batch_block()
    assert "item.get('latitude',item.get('lat'))" in b
    assert "item.get('longitude',item.get('lon',item.get('lng')))" in b
    assert "item.get('accuracy_m',item.get('accuracy',0))" in b
    assert "item.get('speed_kmh',item.get('speed',0))" in b

def test_valid_points_are_still_stored_and_duplicates_safe():
    b=batch_block()
    assert 'existing_locations' in b and 'sequence in existing_locations' in b
    assert 'db.session.add(Location(' in b
    assert 'accepted.append(sequence)' in b
    assert "status='processed'" in b
