import logging,requests
log=logging.getLogger('AssetTrackEdge')
def build(cfg):
 s=requests.Session();s.headers.update({'User-Agent':'AssetTrackEdgeGateway/REV20C'})
 proxy=(cfg.get('proxy') or {}).get('url','').strip()
 if proxy:s.proxies.update({'http':proxy,'https':proxy});log.info('HTTP transport mode EXPLICIT_PROXY')
 else:log.info('HTTP transport mode DIRECT_OR_ENV')
 s.verify=(cfg.get('proxy') or {}).get('verify_tls',True)
 return s
def health(session,base,timeout=30):
 r=session.get(base.rstrip('/')+'/health',timeout=timeout);r.raise_for_status();return r.json()
