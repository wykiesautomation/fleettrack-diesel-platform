from pathlib import Path


def test_mobile_batch_avoids_point_loop_n_plus_one_queries():
    source = Path("app/routes.py").read_text(encoding="utf-8")
    start = source.index("def mobile_tracker_location_batch():")
    end = source.index("def mobile_tracking_start():", start)
    route = source[start:end]
    assert "existing_locations" in route
    assert "signal_map" in route
    assert "existing_readings" in route
    assert "latest_eval_item" in route
    assert route.count("evaluate_mobile(device,") == 1
    assert "Location.query.filter_by(asset_id=device.asset_id,sequence=sequence).first()" not in route
    assert "SignalDefinition.query.filter_by(customer_id=device.customer_id,asset_id=device.asset_id,key=key).first()" not in route


def test_remote_postgres_has_bounded_connection_and_statement_waits():
    source = Path("app/__init__.py").read_text(encoding="utf-8")
    assert '"connect_timeout": 10' in source
    assert 'statement_timeout=25000' in source
