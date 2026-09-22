from __future__ import annotations
import uuid
from typing import Any
from .browser_runtime import BrowserRuntime
from .locator_resolver import LocatorResolver
from ..artifact_service import ArtifactService
from ..config import BROWSER_HEADLESS,BROWSER_TIMEOUT_MS
from ..execution.probe_service import ProbeService

class BrowserService:
    def __init__(self,runtime:BrowserRuntime,artifacts:ArtifactService,probes:ProbeService): self.runtime=runtime; self.artifacts=artifacts; self.probes=probes; self.playwright=None; self.sessions={}
    def start(self): self.runtime.start()
    def close(self):
        try:self.runtime.call(self._close_all())
        except Exception:pass
        self.runtime.stop()
    def execute(self,command:str,payload:dict[str,Any]): return self.runtime.call(self._execute(command,payload),timeout=max(30,float(payload.get("timeout_seconds") or 0)+5))
    async def _execute(self,c,p):
        if c=="START_BROWSER": return await self._start_browser(p)
        sid=p.get("browser_session_id") or p.get("session_id"); s=self._session(sid); page=s["page"]; timeout=p.get("timeout_ms") or BROWSER_TIMEOUT_MS
        if c=="OPEN_PAGE": self.probes.validate_url(p["url"]); r=await page.goto(p["url"],wait_until=p.get("wait_until","domcontentloaded"),timeout=timeout); return {**await self._state(s),"status_code":r.status if r else None}
        if c=="GET_PAGE_STATE": return await self._state(s)
        if c=="GET_ACCESSIBILITY_TREE": return {"tree":await page.locator("body").aria_snapshot(timeout=timeout)}
        if c=="GET_CONSOLE_LOGS": return {"logs":s["console"]}
        if c=="GET_NETWORK_ERRORS": return {"errors":s["network"]}
        if c=="TAKE_PAGE_SCREENSHOT":
            loc=LocatorResolver.resolve(page,p.get("locator")) if p.get("locator") else page; data=await loc.screenshot(full_page=p.get("full_page",True)) if loc is page else await loc.screenshot(); return self.artifacts.create_bytes(data,kind="browser_screenshot",suffix=".png",source={"browser_session_id":sid})
        if c=="CLOSE_BROWSER": await s["context"].close(); await s["browser"].close(); self.sessions.pop(sid,None); return {"closed":sid}
        loc=LocatorResolver.resolve(page,p.get("locator")) if p.get("locator") else None
        if c=="CLICK_ELEMENT": await loc.click(timeout=timeout); return {"clicked":True}
        if c=="FILL_INPUT": await loc.fill(str(p.get("input_text","")),timeout=timeout); return {"filled":True}
        if c=="SELECT_OPTION": return {"selected":await loc.select_option(str(p.get("value","")),timeout=timeout)}
        if c=="CHECK_ELEMENT": await loc.check(timeout=timeout); return {"checked":True}
        if c=="UNCHECK_ELEMENT": await loc.uncheck(timeout=timeout); return {"checked":False}
        if c=="PRESS_KEY": await (loc or page).press(p.get("key",""),timeout=timeout); return {"pressed":p.get("key")}
        if c=="WAIT_FOR_ELEMENT": await loc.wait_for(state=p.get("state","visible"),timeout=timeout); return {"ready":True}
        if c=="GET_ELEMENT_TEXT": return {"text":await loc.inner_text(timeout=timeout)}
        if c=="GET_ELEMENT_VALUE": return {"value":await loc.input_value(timeout=timeout),"checked":await loc.is_checked() if await loc.get_attribute("type") in {"checkbox","radio"} else None}
        if c=="GET_TABLE_DATA": return await self._table(loc)
        raise ValueError(f"지원하지 않는 BROWSER 명령이다: {c}")
    async def _start_browser(self,p):
        if self.playwright is None:
            from playwright.async_api import async_playwright
            self.playwright=await async_playwright().start()
        name=p.get("browser_name","chromium"); viewport=p.get("viewport") or {"width":p.get("viewport_width",1440),"height":p.get("viewport_height",1000)}; engine=getattr(self.playwright,name); browser=await engine.launch(headless=p.get("headless",BROWSER_HEADLESS)); context=await browser.new_context(viewport={"width":int(viewport.get("width",1440)),"height":int(viewport.get("height",1000))}); page=await context.new_page(); sid="browser_"+uuid.uuid4().hex; session={"browser":browser,"context":context,"page":page,"console":[],"network":[]}; page.on("console",lambda m:session["console"].append({"type":m.type,"text":m.text})); page.on("pageerror",lambda e:session["console"].append({"type":"pageerror","text":str(e)})); page.on("requestfailed",lambda r:session["network"].append({"url":r.url,"error":r.failure})); page.on("response",lambda r:session["network"].append({"url":r.url,"status":r.status}) if r.status>=400 else None); self.sessions[sid]=session; return {"browser_session_id":sid,"status":"READY","browser_name":name}
    async def _state(self,s):
        page=s["page"]; return {"url":page.url,"title":await page.title(),"ready_state":await page.evaluate("document.readyState"),"visible_text":(await page.locator("body").inner_text())[:50000],"console_error_count":len([x for x in s["console"] if x["type"] in {"error","pageerror"}]),"network_error_count":len(s["network"])}
    async def _table(self,loc):
        headers=await loc.locator("thead th").all_inner_texts(); rows=[]
        for row in await loc.locator("tbody tr").all(): rows.append(await row.locator("th,td").all_inner_texts())
        return {"headers":headers,"rows":[dict(zip(headers,r)) if headers else r for r in rows]}
    def _session(self,sid):
        if sid not in self.sessions: raise FileNotFoundError(f"브라우저 세션을 찾을 수 없다: {sid}")
        return self.sessions[sid]
    async def _close_all(self):
        for sid in list(self.sessions):
            s=self.sessions.pop(sid)
            try:await s["context"].close(); await s["browser"].close()
            except Exception:pass
        if self.playwright: await self.playwright.stop(); self.playwright=None
