import threading,tkinter as tk,uvicorn
from liq_analysis_server.api import app
from liq_analysis_server.config import SERVER_HOST,SERVER_PORT
from liq_analysis_server.ui import ActionEditorUI
def main():
    server=uvicorn.Server(uvicorn.Config(app,host=SERVER_HOST,port=SERVER_PORT,log_level="info"));threading.Thread(target=server.run,daemon=True).start();root=tk.Tk();ActionEditorUI(root);root.mainloop();server.should_exit=True
if __name__=="__main__":main()

