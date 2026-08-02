import os, hashlib, socket
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

SANDBOX_PROCESS='https://sandbox.payfast.co.za/eng/process'
LIVE_PROCESS='https://www.payfast.co.za/eng/process'
SANDBOX_VALIDATE='https://sandbox.payfast.co.za/eng/query/validate'
LIVE_VALIDATE='https://www.payfast.co.za/eng/query/validate'
PF_HOSTS=('www.payfast.co.za','sandbox.payfast.co.za','w1w.payfast.co.za','w2w.payfast.co.za')

def config():
    mode=os.getenv('PAYFAST_MODE','sandbox').strip().lower()
    return {'mode':mode,'sandbox':mode!='live','merchant_id':os.getenv('PAYFAST_MERCHANT_ID','').strip(),'merchant_key':os.getenv('PAYFAST_MERCHANT_KEY','').strip(),'passphrase':os.getenv('PAYFAST_PASSPHRASE','').strip(),'base_url':os.getenv('APP_BASE_URL','https://fleettrack.wykiesautomation.co.za').rstrip('/'),'validate_ip':os.getenv('PAYFAST_VALIDATE_IP','false').lower()=='true'}

def endpoint(cfg): return SANDBOX_PROCESS if cfg['sandbox'] else LIVE_PROCESS

def clean_pairs(data, preserve_order=False):
    pairs=data.items() if hasattr(data,'items') else data
    out=[(str(k),str(v)) for k,v in pairs if k!='signature' and v is not None and str(v)!='']
    return out if preserve_order else sorted(out,key=lambda x:x[0])

def parameter_string(data, passphrase='', preserve_order=False):
    pairs=clean_pairs(data,preserve_order)
    text='&'.join(f'{quote_plus(k)}={quote_plus(v)}' for k,v in pairs)
    if passphrase: text += '&passphrase='+quote_plus(passphrase)
    return text

def signature(data, passphrase='', preserve_order=False): return hashlib.md5(parameter_string(data,passphrase,preserve_order).encode()).hexdigest()

def build_checkout(subscription,payment,user,cfg):
    name_parts=(user.name or 'Customer').split(' ',1)
    data={'merchant_id':cfg['merchant_id'],'merchant_key':cfg['merchant_key'],'return_url':cfg['base_url']+'/billing/success','cancel_url':cfg['base_url']+'/billing/cancel','notify_url':cfg['base_url']+'/payfast/notify','name_first':name_parts[0],'name_last':name_parts[1] if len(name_parts)>1 else '', 'email_address':user.email,'m_payment_id':payment.merchant_payment_id,'amount':f'{payment.amount_gross:.2f}','item_name':f'AssetTrack 360 {subscription.plan.name}','item_description':f'Monthly AssetTrack 360 subscription for customer {subscription.customer_id}','custom_int1':subscription.customer_id,'custom_int2':subscription.id,'subscription_type':'1','billing_date':'','recurring_amount':f'{payment.amount_gross:.2f}','frequency':'3','cycles':'0'}
    data={k:v for k,v in data.items() if v!=''};data['signature']=signature(data,cfg['passphrase'])
    return endpoint(cfg),data

def event_hash(form):
    return hashlib.sha256(urlencode(sorted((str(k),str(v)) for k,v in form.items())).encode()).hexdigest()

def valid_signature(form,cfg):
    supplied=form.get('signature','').lower()
    # PayFast ITN data order must be retained when rebuilding the signature.
    calculated=signature(list(form.items()),cfg['passphrase'],preserve_order=True)
    return bool(supplied and supplied==calculated)

def forwarded_ip(req):
    value=req.headers.get('CF-Connecting-IP') or req.headers.get('X-Forwarded-For') or req.remote_addr or ''
    return value.split(',')[0].strip()

def allowed_ips():
    found=set()
    for host in PF_HOSTS:
        try:
            for item in socket.getaddrinfo(host,443): found.add(item[4][0])
        except OSError: pass
    return found

def valid_source(req,cfg):
    if cfg['sandbox'] and not cfg['validate_ip']: return True
    return forwarded_ip(req) in allowed_ips()

def server_validate(form,cfg):
    url=SANDBOX_VALIDATE if cfg['sandbox'] else LIVE_VALIDATE
    body=urlencode([(k,v) for k,v in form.items()]).encode()
    try:
        response=urlopen(Request(url,data=body,headers={'Content-Type':'application/x-www-form-urlencoded','User-Agent':'AssetTrack360/REV16'}),timeout=15)
        return response.read().decode().strip().upper()=='VALID'
    except Exception:
        return False
