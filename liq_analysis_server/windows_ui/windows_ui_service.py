from __future__ import annotations
import re,time
from .control_locator import ControlLocator
from .window_registry import WindowRegistry
from .screenshot_service import ScreenshotService

class WindowsUIService:
    def __init__(self,processes,registry:WindowRegistry,screenshots:ScreenshotService):self.processes=processes;self.registry=registry;self.screenshots=screenshots
    def _desktop(self):
        try:
            from pywinauto import Desktop; return Desktop(backend="uia")
        except ImportError as exc:raise RuntimeError("pywinauto가 설치되지 않았다") from exc
    def list_windows(self,process_id=""):
        managed_sets={}
        for record in self.processes.list():
            pids={record["pid"]}
            try:pids.update(x["pid"] for x in self.processes.tree(record["process_id"])["children"])
            except Exception:pass
            managed_sets[record["process_id"]]=pids
        allowed=managed_sets.get(process_id) if process_id else None
        rows=[]
        for w in self._desktop().windows():
            try:
                pid=w.process_id()
                if allowed and pid not in allowed:continue
                managed=next((mid for mid,pids in managed_sets.items() if pid in pids),"")
                if not managed:continue
                wid=self.registry.register(w,managed); rows.append({"window_id":wid,"process_id":managed,"pid":pid,"hwnd":int(w.handle),"title":w.window_text(),"visible":w.is_visible(),"enabled":w.is_enabled()})
            except Exception:continue
        return rows
    def wait_for_window(self,process_id,title="",regex="",timeout=20):
        end=time.monotonic()+float(timeout)
        while time.monotonic()<end:
            for row in self.list_windows(process_id):
                if (regex and re.search(regex,row["title"])) or (not regex and (not title or title in row["title"])):return row
            time.sleep(.25)
        raise TimeoutError("Windows 창 대기 시간이 초과되었다")
    def state(self,wid):
        x=self.registry.get(wid);w=x["wrapper"];return {"window_id":wid,"process_id":x["process_id"],"pid":x["pid"],"hwnd":x["hwnd"],"title":w.window_text(),"visible":w.is_visible(),"enabled":w.is_enabled(),"responsive":w.exists(timeout=.5)}
    def tree(self,wid,max_depth=6,max_nodes=500):
        root=self.registry.get(wid)["wrapper"];nodes=[]
        def walk(node,path,depth):
            if depth>max_depth or len(nodes)>=max_nodes:return
            try: info=node.element_info; nodes.append({"control_path":path,"title":node.window_text(),"control_type":info.control_type,"automation_id":info.automation_id,"class_name":info.class_name,"enabled":node.is_enabled(),"visible":node.is_visible()})
            except Exception:return
            for i,c in enumerate(node.children()):walk(c,[*path,i],depth+1)
        walk(root,[],0);return {"window_id":wid,"nodes":nodes,"truncated":len(nodes)>=max_nodes}
    def control(self,wid,spec):return ControlLocator.find(self.registry.get(wid)["wrapper"],spec)
    def click(self,wid,spec):
        c=self.control(wid,spec)
        try:c.invoke()
        except Exception:c.click_input()
        return {"clicked":True}
    def set_text(self,wid,spec,text):c=self.control(wid,spec);c.set_edit_text(text);return {"text":text}
    def select(self,wid,spec,value):c=self.control(wid,spec);c.select(value);return {"selected":value}
    def value(self,wid,spec):
        c=self.control(wid,spec);info=c.element_info;result={"name":c.window_text(),"control_type":info.control_type,"automation_id":info.automation_id,"enabled":c.is_enabled(),"visible":c.is_visible()}
        try:result["value"]=c.get_value()
        except Exception:
            try:result["value"]=c.selected_text()
            except Exception:result["value"]=c.window_text()
        try:result["checked"]=c.get_toggle_state()!=0
        except Exception:pass
        return result
    def press(self,wid,spec,key):c=self.control(wid,spec) if spec else self.registry.get(wid)["wrapper"];c.type_keys(key,with_spaces=True);return {"pressed":key}
    def screenshot(self,wid,spec=None):w=self.control(wid,spec) if spec else self.registry.get(wid)["wrapper"];return self.screenshots.capture(w,{"window_id":wid})
    def close_window(self,wid):self.registry.get(wid)["wrapper"].close();return {"closed":wid}
