import hashlib
import os
import socket
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

SANDBOX_PROCESS = 'https://sandbox.payfast.co.za/eng/process'
LIVE_PROCESS = 'https://www.payfast.co.za/eng/process'
SANDBOX_VALIDATE = 'https://sandbox.payfast.co.za/eng/query/validate'
LIVE_VALIDATE = 'https://www.payfast.co.za/eng/query/validate'


def config():
    mode = os.getenv('PAYFAST_MODE', 'sandbox').strip().lower()
    return {
        'mode': mode,
        'sandbox': mode != 'live',
        'merchant_id': os.getenv('PAYFAST_MERCHANT_ID', '').strip(),
        'merchant_key': os.getenv('PAYFAST_MERCHANT_KEY', '').strip(),
        'passphrase': os.getenv('PAYFAST_PASSPHRASE', '').strip(),
        'base_url': os.getenv(
            'APP_BASE_URL',
            'https://fleettrack.wykiesautomation.co.za',
        ).strip().rstrip('/'),
        'validate_ip': os.getenv('PAYFAST_VALIDATE_IP', 'false').strip().lower()
        == 'true',
    }


def _ordered_pairs(data):
    """Return non-empty PayFast fields in the exact submitted order."""
    source = data.items() if hasattr(data, 'items') else data
    return [
        (str(key), str(value).strip())
        for key, value in source
        if key != 'signature' and value is not None and str(value).strip() != ''
    ]


def parameter_string(data, passphrase=''):
    """Build the exact form-encoded string PayFast signs."""
    text = '&'.join(
        f'{key}={quote_plus(value)}' for key, value in _ordered_pairs(data)
    )
    if passphrase:
        text += '&passphrase=' + quote_plus(passphrase.strip())
    return text


def signature(data, passphrase=''):
    """Generate the lower-case MD5 signature without re-sorting form fields."""
    return hashlib.md5(parameter_string(data, passphrase).encode('utf-8')).hexdigest()


def build_checkout(subscription, payment, user, cfg):
    name_parts = (user.name or 'Customer').split(' ', 1)
    fields = {
        'merchant_id': cfg['merchant_id'],
        'merchant_key': cfg['merchant_key'],
        'return_url': cfg['base_url'] + '/billing/success',
        'cancel_url': cfg['base_url'] + '/billing/cancel',
        'notify_url': cfg['base_url'] + '/payfast/notify',
        'name_first': name_parts[0],
        'name_last': name_parts[1] if len(name_parts) > 1 else '',
        'email_address': user.email,
        'm_payment_id': payment.merchant_payment_id,
        'amount': f'{payment.amount_gross:.2f}',
        'item_name': f'AssetTrack 360 {subscription.plan.name}',
        'custom_int1': subscription.customer_id,
        'custom_int2': subscription.id,
        'subscription_type': '1',
        'recurring_amount': f'{payment.amount_gross:.2f}',
        'frequency': '3',
        'cycles': '0',
    }
    fields = {key: value for key, value in fields.items() if value not in ('', None)}
    fields['signature'] = signature(fields, cfg['passphrase'])
    endpoint = SANDBOX_PROCESS if cfg['sandbox'] else LIVE_PROCESS
    return endpoint, fields


def event_hash(form):
    pairs = sorted((str(key), str(value)) for key, value in form.items())
    return hashlib.sha256(urlencode(pairs).encode('utf-8')).hexdigest()


def valid_signature(form, cfg):
    supplied = form.get('signature', '').strip().lower()
    calculated = signature(list(form.items()), cfg['passphrase'])
    return bool(supplied and supplied == calculated)


def forwarded_ip(req):
    value = (
        req.headers.get('CF-Connecting-IP')
        or req.headers.get('X-Forwarded-For')
        or req.remote_addr
        or ''
    )
    return value.split(',')[0].strip()


def valid_source(req, cfg):
    if cfg['sandbox'] and not cfg['validate_ip']:
        return True
    allowed = set()
    for host in (
        'www.payfast.co.za',
        'sandbox.payfast.co.za',
        'w1w.payfast.co.za',
        'w2w.payfast.co.za',
    ):
        try:
            for result in socket.getaddrinfo(host, 443):
                allowed.add(result[4][0])
        except OSError:
            pass
    return forwarded_ip(req) in allowed


def server_validate(form, cfg):
    endpoint = SANDBOX_VALIDATE if cfg['sandbox'] else LIVE_VALIDATE
    body = urlencode(list(form.items())).encode('utf-8')
    request = Request(
        endpoint,
        data=body,
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'AssetTrack360/REV18A',
        },
    )
    try:
        response = urlopen(request, timeout=15)
        return response.read().decode().strip().upper() == 'VALID'
    except Exception:
        return False
