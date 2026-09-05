import json,tkinter as tk
from tkinter import ttk
from .config import load
from .queue_store import depth
class App(tk.Tk):
 def __init__(self):
  super().__init__();self.title('AssetTrack 360 Edge Gateway');self.geometry('720x420');self.configure(bg='#061522');cfg=load();ttk.Label(self,text='AssetTrack 360 Edge Gateway',font=('Segoe UI',20,'bold')).pack(pady=18);self.text=tk.Text(self,height=14,width=82);self.text.pack(padx=20,pady=10);self.text.insert('1.0',json.dumps({'gateway_uid':cfg.get('gateway_uid'),'cloud_url':cfg.get('cloud_url'),'queue_depth':depth(),'access':'READ-ONLY','write_enabled':False},indent=2));self.text.config(state='disabled')
if __name__=='__main__':App().mainloop()
