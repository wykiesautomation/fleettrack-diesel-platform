"""Read-only Modbus RTU commissioning simulator for a configured virtual serial pair."""
import argparse,asyncio,math,time
from pymodbus.datastore import ModbusSequentialDataBlock,ModbusSlaveContext,ModbusServerContext
from pymodbus.server import StartAsyncSerialServer
async def serve(port,baudrate=9600):
    store=ModbusSlaveContext(di=ModbusSequentialDataBlock(0,[0]*200),co=ModbusSequentialDataBlock(0,[0]*200),hr=ModbusSequentialDataBlock(0,[0]*200),ir=ModbusSequentialDataBlock(0,[0]*200));context=ModbusServerContext(slaves={1:store},single=False)
    async def update():
        start=time.time()
        while True:
            t=time.time()-start;store.setValues(3,0,[int((5.62+.15*math.sin(t/12))*100),int((148.4+3*math.sin(t/18))*10),int((61.3+.4*math.sin(t/40))*10),int((72.5+1.5*math.sin(t/90))*10)]);store.setValues(1,0,[True]);store.setValues(4,0,[int((34.7+math.sin(t/8))*10)]);await asyncio.sleep(1)
    asyncio.create_task(update());print(f'AssetTrack 360 Modbus RTU simulator READ-ONLY on {port} at {baudrate} 8N1, Slave 1');await StartAsyncSerialServer(context=context,port=port,baudrate=baudrate,bytesize=8,parity='N',stopbits=1,timeout=1)
def main():
    p=argparse.ArgumentParser();p.add_argument('--port',required=True);p.add_argument('--baudrate',type=int,default=9600);a=p.parse_args();asyncio.run(serve(a.port,a.baudrate))
if __name__=='__main__':main()
