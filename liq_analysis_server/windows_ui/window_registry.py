from __future__ import annotations
import uuid
class WindowRegistry:
    def __init__(self): self.windows={}
    def register(self,wrapper,process_id):
        hwnd=int(wrapper.handle); existing=next((k for k,v in self.windows.items() if v["hwnd"]==hwnd),None)
        wid=existing or "win_"+uuid.uuid4().hex; self.windows[wid]={"window_id":wid,"hwnd":hwnd,"pid":wrapper.process_id(),"process_id":process_id,"wrapper":wrapper}; return wid
    def get(self,wid):
        if wid not in self.windows: raise FileNotFoundError(f"창을 찾을 수 없다: {wid}")
        return self.windows[wid]

