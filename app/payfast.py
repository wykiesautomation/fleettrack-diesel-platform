import os,hashlib,socket
from urllib.parse import quote_plus,urlencode
from urllib.request import Request,urlopen
SANDBOX_PROCESS='https://sandbox.payfast.co.za/eng/process';LIVE_PROCESS='https://www.payfast.co.za/eng/process';SANDBOX_VALIDATE='https://sandbox.payfast.co.za/eng/query/validate';LIVE_VALIDATE='https://www.payfast.co.za/eng/query/validate'
def config():
 m=os.getenv('PAYFAST_MODE','sandbox').lower();return {'mode':m,'sandbox':m!='live','merchant_id':os.getenv('PAYFAST_MERCHANT_ID','').strip(),'merchant_key':os.getenv('PAYFAST_MERCHANT_KEY','').strip(),'passphrase':os.getenv('PAYFAST_PASSPHRASE','').strip(),'base_url':os.getenv('APP_BASE_URL','https://fleettrack.wykiesautomation.co.za').rstrip('/'),'validate_ip':os.getenv('PAYFAST_VALIDATE_IP','false').lower()=='true'}
def signature(data,phrase='',ordered=False):
 pairs=[(str(k),str(v)) for k,v in (data.items() if hasattr(data,'items') else data) if k!='signature' and v not in (None,'')]
 if not ordered:pairs.sort(key=lambda x:x[0])
 text='&'.join(f'{quote_plus(k)}={quote_plus(v)}' for k,v in pairs)+(('&passphrase='+quote_plus(phrase)) if phrase else '')
 return hashlib.md5(text.encode()).hexdigest()
def build_checkout(sub,payment,user,cfg):
 n=(user.name or 'Customer').split(' ',1);d={'merchant_id':cfg['merchant_id'],'merchant_key':cfg['merchant_key'],'return_url':cfg['base_url']+'/billing/success','cancel_url':cfg['base_url']+'/billing/cancel','notify_url':cfg['base_url']+'/payfast/notify','name_first':n[0],'name_last':n[1] if len(n)>1 else '', 'email_address':user.email,'m_payment_id':payment.merchant_payment_id,'amount':f'{payment.amount_gross:.2f}','item_name':f'AssetTrack 360 {sub.plan.name}','custom_int1':sub.customer_id,'custom_int2':sub.id,'subscription_type':'1','recurring_amount':f'{payment.amount_gross:.2f}','frequency':'3','cycles':'0'};d={k:v for k,v in d.items() if v!=''};d['signature']=signature(d,cfg['passphrase']);return (SANDBOX_PROCESS if cfg['sandbox'] else LIVE_PROCESS),d
def event_hash(form):return hashlib.sha256(urlencode(sorted((str(k),str(v)) for k,v in form.items())).encode()).hexdigest()
def valid_signature(form,cfg):return form.get('signature','').lower()==signature(list(form.items()),cfg['passphrase'],True)
def forwarded_ip(req):return (req.headers.get('CF-Connecting-IP') or req.headers.get('X-Forwarded-For') or req.remote_addr or '').split(',')[0].strip()
def valid_source(req,cfg):
 if cfg['sandbox'] and not cfg['validate_ip']:return True
 ips=set()
 for host in ('www.payfast.co.za','sandbox.payfast.co.za','w1w.payfast.co.za','w2w.payfast.co.za'):
  try:
   for x in socket.getaddrinfo(host,443):ips.add(x[4][0])
  except OSError:pass
 return forwarded_ip(req) in ips
def server_validate(form,cfg):
 try:return urlopen(Request(SANDBOX_VALIDATE if cfg['sandbox'] else LIVE_VALIDATE,data=urlencode(list(form.items())).encode(),headers={'Content-Type':'application/x-www-form-urlencoded','User-Agent':'AssetTrack360/REV17'}),timeout=15).read().decode().strip().upper()=='VALID'
 except Exception:return False
