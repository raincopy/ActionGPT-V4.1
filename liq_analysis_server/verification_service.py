from __future__ import annotations
import re
from typing import Any
class VerificationService:
    def verify(self,actual:Any,assertions:list[Any]):
        results=[]
        for a in assertions:
            spec=a.model_dump() if hasattr(a,"model_dump") else dict(a); value=self._field(actual,spec.get("field", "")); expected=spec.get("expected"); op=spec.get("operator","equals"); left=value
            if not spec.get("case_sensitive",True) and isinstance(left,str) and isinstance(expected,str): left,expected=left.lower(),expected.lower()
            checks={"equals":lambda:left==expected,"not_equals":lambda:left!=expected,"contains":lambda:expected in left,"not_contains":lambda:expected not in left,"regex":lambda:bool(re.search(str(expected),str(left))),"exists":lambda:left is not None,"not_exists":lambda:left is None,"empty":lambda:left in (None,"",[],{}),"not_empty":lambda:left not in (None,"",[],{}),"gt":lambda:left>expected,"gte":lambda:left>=expected,"lt":lambda:left<expected,"lte":lambda:left<=expected}
            try: passed=bool(checks[op]())
            except Exception: passed=False
            results.append({"field":spec.get("field",""),"operator":op,"expected":expected,"actual":value,"passed":passed})
        return {"verified":all(x["passed"] for x in results),"assertions":results,"actual":actual}
    def _field(self,obj,path):
        if not path:return obj
        cur=obj
        for part in path.split("."):
            if isinstance(cur,dict):cur=cur.get(part)
            elif isinstance(cur,list) and part.isdigit():cur=cur[int(part)]
            else:return None
        return cur
