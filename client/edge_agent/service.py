import json
import logging
import time
import traceback

import requests
from logging.handlers import RotatingFileHandler

from .config import BASE, ensure, load, load_secrets
from .connectors.modbus import read as modbus_read
from .connectors.opcua import read as opc_read
from .connectors.sqlcsv import csv_read, sql
from .queue_store import batch, depth, fail, ok, put

ensure()
log = logging.getLogger('AssetTrackEdge')
log.setLevel(logging.INFO)
handler = RotatingFileHandler(BASE / 'logs' / 'gateway.log', maxBytes=5_000_000, backupCount=5)
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
if not log.handlers:
    log.addHandler(handler)

HEARTBEAT_PATH = '/api/v1/gateways/heartbeat'
INGEST_PATH = '/api/v1/gateways/ingest'


def collect(connector, secrets):
    if connector['type'] in ('MODBUS_TCP', 'MODBUS_RTU'):
        return modbus_read(connector)
    if connector['type'] == 'OPC_UA':
        return opc_read(connector, secrets)
    if connector['type'] == 'SQL_ODBC':
        return sql(connector, secrets)
    if connector['type'] == 'CSV':
        return csv_read(connector)
    raise ValueError('Unsupported connector ' + connector['type'])


def cloud_session():
    session = requests.Session()
    session.headers.update({'User-Agent': 'AssetTrackEdgeGateway/REV20A2'})
    return session


def upload(cfg, secrets, session):
    token = secrets.get('edge_api_token', '').strip()
    url = cfg['cloud_url'].rstrip('/') + INGEST_PATH
    for row_id, payload, attempts in batch():
        try:
            response = session.post(
                url,
                json=json.loads(payload),
                headers={'Authorization': 'Bearer ' + token},
                timeout=90,
            )
            response.raise_for_status()
            ok(row_id)
            log.info('Upload accepted using REV20A2 endpoint')
        except Exception as exc:
            fail(row_id, exc)
            log.warning('Upload failed: %s', exc)
            break


def heartbeat(cfg, secrets, session):
    token = secrets.get('edge_api_token', '').strip()
    url = cfg['cloud_url'].rstrip('/') + HEARTBEAT_PATH
    try:
        response = session.post(
            url,
            json={
                'version': '1.0.2',
                'capabilities': ['OPC_UA', 'MODBUS_TCP', 'MODBUS_RTU', 'SQL_ODBC', 'CSV'],
                'queue_depth': depth(),
                'gateway_id': cfg.get('gateway_id'),
            },
            headers={'Authorization': 'Bearer ' + token},
            timeout=90,
        )
        response.raise_for_status()
        data = response.json()
        log.info(
            'Heartbeat accepted gateway=%s api=%s',
            data.get('gateway_id'),
            data.get('api_revision'),
        )
        return True
    except Exception as exc:
        log.warning('Heartbeat failed: %s', exc)
        return False


def cycle(session=None):
    cfg = load()
    secrets = load_secrets()
    session = session or cloud_session()
    for connector in cfg.get('connectors', []):
        if not connector.get('enabled', True):
            continue
        try:
            points = collect(connector, secrets)
            put({
                'connector_key': connector['connector_key'],
                'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'points': points,
            })
            log.info('%s collected %s points', connector.get('name'), len(points))
        except Exception as exc:
            log.error('%s collection failed: %s', connector.get('name'), exc)
    upload(cfg, secrets, session)
    heartbeat(cfg, secrets, session)


def run():
    log.info('AssetTrack Edge Gateway REV20A2 starting')
    session = cloud_session()
    while True:
        try:
            cycle(session)
        except Exception:
            log.error(traceback.format_exc())
        time.sleep(max(load().get('scan_seconds', 30), 5))


if __name__ == '__main__':
    run()
