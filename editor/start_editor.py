import http.server
import socketserver
import webbrowser
import os
import threading
import sys

# -------------------------------------------------------------------------
# 純前端啟動器
# 僅負責提供靜態網頁檔案 (HTML/JS/CSS)
# 後端邏輯由 WVD 主程式負責 (ws://localhost:8765)
# -------------------------------------------------------------------------

# 設定 DIST 目錄 (編譯後的網頁檔案)
if getattr(sys, 'frozen', False):
    # PyInstaller 打包環境: EXE 所在目錄
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # 一般 Python 腳本執行: 腳本所在目錄
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DIRECTORY = os.path.join(BASE_DIR, "dist")

# 如果當前目錄下沒找到 (例如開發模式下在 editor/ 中執行)，嘗試在專案結構中尋找
if not os.path.exists(DIRECTORY):
    # 往上一層找 (假設在 editor/ 裡跑，要找 editor/dist)
    # 但這裡邏輯稍顯複雜，不如直接檢查常見路徑
    DEV_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
    if os.path.exists(DEV_DIST):
        DIRECTORY = DEV_DIST
    else:
        # 最後嘗試從專案根目錄找 (d:\Project\wvd\editor\dist)
        PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        ALT_DIR = os.path.join(PROJECT_ROOT, "editor", "dist")
        if os.path.exists(ALT_DIR):
            DIRECTORY = ALT_DIR

PORT = 3000

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def log_message(self, format, *args):
        pass # 保持 Console 乾淨

def open_browser():
    """延遲開啟瀏覽器"""
    import time
    time.sleep(1.0)
    print(f"啟動瀏覽器: http://localhost:{PORT}")
    webbrowser.open(f"http://localhost:{PORT}")

if __name__ == "__main__":
    if not os.path.exists(DIRECTORY):
        print(f"錯誤：找不到 dist 資料夾！")
        print(f"搜尋路徑：{DIRECTORY}")
        sys.exit(1)
    
    print(f"=" * 50)
    print(f"  地城腳本編輯器 (Web UI)")
    print(f"  -----------------------")
    print(f"  網站位置: http://localhost:{PORT}")
    print(f"  資源目錄: {DIRECTORY}")
    print(f"")
    print(f"  [注意] 此程式僅提供操作介面。")
    print(f"  請務必啟動 WVD 主程式以進行存檔與讀取。")
    print(f"=" * 50)
    print(f"\n按 Ctrl+C 停止網頁伺服器\n")
    
    # 背景開啟瀏覽器
    threading.Thread(target=open_browser, daemon=True).start()
    
    # 啟動前端 HTTP Server
    # 允許地址重用，避免重啟時顯示 Address already in use 錯誤 (雖然 HTTP wait wait 較短)
    socketserver.TCPServer.allow_reuse_address = True
    
    try:
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\n網頁伺服器已停止")
    except OSError as e:
         print(f"錯誤: 無法啟動 Port {PORT}。可能編輯器已在運行中? ({e})")
