import http.server
import socketserver
import webbrowser
import os
import threading
import sys
import tkinter as tk
from tkinter import messagebox

# -------------------------------------------------------------------------
# 地城腳本編輯器啟動器 (帶 GUI 控制介面)
# -------------------------------------------------------------------------

# 設定資源路徑
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DIRECTORY = os.path.join(BASE_DIR, "dist")
PORT = 3000

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    def log_message(self, format, *args):
        pass # 保持內部安靜

class EditorControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WVD 腳本編輯器控制台")
        self.root.geometry("350x200")
        self.root.resizable(False, False)
        
        # 設定視窗置中
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = (screen_width // 2) - (350 // 2)
        y = (screen_height // 2) - (200 // 2)
        self.root.geometry(f"350x200+{x}+{y}")

        self.httpd = None
        self.server_thread = None

        # UI 佈局
        self.label_status = tk.Label(root, text="正在啟動伺服器...", font=("Microsoft JhengHei", 12))
        self.label_status.pack(pady=20)

        self.btn_open = tk.Button(root, text="🌍 開啟編輯器網頁", command=self.open_url, 
                                 width=20, height=2, bg="#3b82f6", fg="white", font=("Microsoft JhengHei", 10, "bold"))
        self.btn_open.pack(pady=5)

        self.btn_stop = tk.Button(root, text="❌ 停止並結束程式", command=self.on_closing,
                                 width=20, height=1, bg="#ef4444", fg="white", font=("Microsoft JhengHei", 9))
        self.btn_stop.pack(pady=10)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # 啟動伺服器線程
        self.start_server()

    def start_server(self):
        if not os.path.exists(DIRECTORY):
            messagebox.showerror("錯誤", f"找不到資源資料夾: {DIRECTORY}\n請確保啟動檔旁有 dist 資料夾。")
            sys.exit(1)

        def run_server():
            socketserver.TCPServer.allow_reuse_address = True
            try:
                with socketserver.TCPServer(("", PORT), Handler) as httpd:
                    self.httpd = httpd
                    self.root.after(0, lambda: self.label_status.config(text=f"✅ 編輯器伺服器運行中 (Port {PORT})", fg="#059669"))
                    httpd.serve_forever()
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("伺服器錯誤", f"無法啟動伺服器: {e}"))

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        
        # 自動開啟一次瀏覽器
        self.root.after(1000, self.open_url)

    def open_url(self):
        webbrowser.open(f"http://localhost:{PORT}")

    def on_closing(self):
        """徹底結束程式，不留殘留進程"""
        try:
            self.root.destroy()
        except:
            pass
        import os
        os._exit(0)

if __name__ == "__main__":
    root = tk.Tk()
    app = EditorControlApp(root)
    root.mainloop()
