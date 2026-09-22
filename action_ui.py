import tkinter as tk
from liq_analysis_server.runtime import initialize_runtime,stop_runtime
from liq_analysis_server.ui import ActionEditorUI
if __name__=="__main__":
    initialize_runtime();root=tk.Tk();ActionEditorUI(root);root.mainloop();stop_runtime()

