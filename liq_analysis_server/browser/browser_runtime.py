from __future__ import annotations
import asyncio,threading
class BrowserRuntime:
    def __init__(self): self.loop=None; self.thread=None
    def start(self):
        if self.thread and self.thread.is_alive(): return
        self.loop=asyncio.new_event_loop(); self.thread=threading.Thread(target=self._run,daemon=True,name="liq-playwright"); self.thread.start()
    def _run(self): asyncio.set_event_loop(self.loop); self.loop.run_forever()
    def call(self,coro,timeout=30):
        self.start(); return asyncio.run_coroutine_threadsafe(coro,self.loop).result(timeout=timeout)
    def stop(self):
        if self.loop: self.loop.call_soon_threadsafe(self.loop.stop)
        if self.thread: self.thread.join(timeout=5)

