class ControlLocator:
    @staticmethod
    def find(window,spec):
        s=spec.model_dump() if hasattr(spec,"model_dump") else dict(spec or {})
        if s.get("control_path"):
            cur=window
            for idx in s["control_path"]: cur=cur.children()[int(idx)]
            return cur
        kwargs={}
        for src,dst in (("automation_id","auto_id"),("title","title"),("control_type","control_type"),("class_name","class_name")):
            if s.get(src):kwargs[dst]=s[src]
        matches=window.descendants(**kwargs); idx=int(s.get("found_index",0))
        if idx>=len(matches): raise FileNotFoundError(f"Windows control을 찾을 수 없다: {s}")
        return matches[idx]

