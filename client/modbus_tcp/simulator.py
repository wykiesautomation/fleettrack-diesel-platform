"""Read-only Modbus TCP commissioning simulator."""
import argparse,asyncio,math,time
from pymodbus.datastore import ModbusSequentialDataBlock,ModbusSlaveContext,ModbusServerContext
from pymodbus.server import StartAsyncTcpServer
async def main_async(host,port):
 store=ModbusSlaveContext(di=ModbusSequentialDataBlock(0,[0]*200),co=ModbusSequentialDataBlock(0,[0]*200),hr=ModbusSequentialDataBlock(0,[0]*200),ir=ModbusSequentialDataBlock(0,[0]*200))
 context=ModbusServerContext(slaves={1:store},single=False)
 async def update():
  start=time.time()
  while True:
   t=time.time()-start;store.setValues(3,0,[int((5.62+.18*math.sin(t/12))*100),int((148.4+4*math.sin(t/18))*10),int((61.3+.4*math.sin(t/40))*10),int((72.5+1.5*math.sin(t/90))*10)]);store.setValues(1,0,[True]);store.setValues(4,0,[int((34.7+math.sin(t/8))*10)]);await asyncio.sleep(1)
 asyncio.create_task(update());print(f'AssetTrack 360 Modbus TCP simulator READ-ONLY on {host}:{port}, Unit ID 1');await StartAsyncTcpServer(context=context,address=(host,port))
def main():
 p=argparse.ArgumentParser();p.add_argument('--host',default='0.0.0.0');p.add_argument('--port',type=int,default=1502);a=p.parse_args();asyncio.run(main_async(a.host,a.port))
if __name__=='__main__':main()
