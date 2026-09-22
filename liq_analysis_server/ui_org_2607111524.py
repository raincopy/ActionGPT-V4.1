from __future__ import annotations
import json,os,tkinter as tk
from tkinter import ttk,messagebox
from .config import PROJECT_ROOT,SERVER_PORT
from .runtime import task_manager,process_manager,browser_service,windows_ui_service,artifact_service

class ActionEditorUI:
    def __init__(self,root):
        self.root=root;root.title("Liq-analysis Action GPT v0.2.0");root.geometry("1450x850");self.status=tk.StringVar(value=f"서버 http://127.0.0.1:{SERVER_PORT} | 작업 루트 {PROJECT_ROOT}");ttk.Label(root,textvariable=self.status,padding=8).pack(fill="x");self.tabs=ttk.Notebook(root);self.tabs.pack(fill="both",expand=True,padx=8,pady=8);self.views={}
        for name,cols in (("작업",("ID","API/명령","상태","진행")),("프로세스",("ID","PID","상태","경로")),("브라우저",("ID","URL","제목","오류")),("Windows UI",("ID","PID","제목","상태")),("아티팩트",("ID","종류","크기","생성"))):self._tab(name,cols)
        buttons=ttk.Frame(root,padding=8);buttons.pack(fill="x");ttk.Button(buttons,text="새로고침",command=self.refresh).pack(side="left");ttk.Button(buttons,text="선택 프로세스 종료",command=self.stop_process).pack(side="left",padx=6);ttk.Button(buttons,text="선택 아티팩트 열기",command=self.open_artifact).pack(side="left");self.detail=tk.Text(root,height=10,wrap="none");self.detail.pack(fill="x",padx=8,pady=(0,8));self.refresh();root.after(1000,self._poll)
    def _tab(self,name,cols):
        f=ttk.Frame(self.tabs);self.tabs.add(f,text=name);tree=ttk.Treeview(f,columns=cols,show="headings");[tree.heading(c,text=c) for c in cols];tree.pack(fill="both",expand=True);tree.bind("<<TreeviewSelect>>",self._detail);self.views[name]=tree
    def refresh(self):
        data={"작업":[(x["task_id"],f'{x["api_name"]}/{x["command_code"]}',x["status"],x["progress"]) for x in task_manager.list()],"프로세스":[(x["process_id"],x["pid"],x["status"],x.get("path","")) for x in process_manager.list()],"브라우저":[(k,v["page"].url,"Playwright",len(v["console"])+len(v["network"])) for k,v in browser_service.sessions.items()],"Windows UI":[(x["window_id"],x["pid"],x["wrapper"].window_text(),"관리") for x in windows_ui_service.registry.windows.values()],"아티팩트":[(x["artifact_id"],x["type"],x["size"],x["created_at"]) for x in artifact_service.list()]}
        for name,rows in data.items():
            tree=self.views[name];tree.delete(*tree.get_children());[tree.insert("", "end",iid=str(r[0]),values=r) for r in rows]
    def _detail(self,event):
        tree=event.widget;s=tree.selection()
        if not s:return
        iid=s[0];obj=next((x for x in task_manager.list() if x["task_id"]==iid),None) or next((x for x in process_manager.list() if x["process_id"]==iid),None)
        if not obj:
            try:obj=artifact_service.info(iid)
            except Exception:obj={"id":iid}
        self.detail.delete("1.0","end");self.detail.insert("1.0",json.dumps(obj,ensure_ascii=False,indent=2,default=str))
    def stop_process(self):
        s=self.views["프로세스"].selection()
        if s:
            try:process_manager.stop(s[0]);self.refresh()
            except Exception as e:messagebox.showerror("종료 실패",str(e))
    def open_artifact(self):
        s=self.views["아티팩트"].selection()
        if s:
            try:p,_=artifact_service.file(s[0]);os.startfile(str(p))
            except Exception as e:messagebox.showerror("열기 실패",str(e))
    def _poll(self):self.refresh();self.root.after(1000,self._poll)

