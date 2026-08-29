import argparse,getpass
from .config import bootstrap,load
from .agent import Agent
def main():
 p=argparse.ArgumentParser(prog='assettrack-edge');sub=p.add_subparsers(dest='cmd',required=True)
 b=sub.add_parser('bootstrap');b.add_argument('--cloud',required=True);b.add_argument('--gateway-uid',required=True);b.add_argument('--token')
 sub.add_parser('run');sub.add_parser('status')
 a=p.parse_args()
 if a.cmd=='bootstrap':bootstrap(a.cloud,a.gateway_uid,a.token or getpass.getpass('One-time gateway token: '));print('Gateway configuration saved locally.')
 elif a.cmd=='status':print(load())
 else:Agent().run()
if __name__=='__main__':main()
