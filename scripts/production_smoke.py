import argparse,json,urllib.request,urllib.error
p=argparse.ArgumentParser();p.add_argument('--base',required=True);a=p.parse_args();base=a.base.rstrip('/');failed=0
for path,expected in [('/health',200),('/ready',200),('/',200),('/login',200),('/terms',200),('/privacy',200),('/payment-policy',200)]:
 try:
  r=urllib.request.urlopen(base+path,timeout=30);code=r.status;body=r.read(300).decode(errors='ignore')
 except urllib.error.HTTPError as e:code=e.code;body=e.read(300).decode(errors='ignore')
 ok=code==expected;failed+=not ok;print(('PASS' if ok else 'FAIL'),path,code,body[:80].replace('\n',' '))
raise SystemExit(1 if failed else 0)
