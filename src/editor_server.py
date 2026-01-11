"""
Quest 編輯器 WebSocket 伺服器 (強化日誌與穩定版)
"""
import asyncio
import json
import logging
import threading
import time
import os
import sys
from typing import Set, Callable, Optional

# 強制獲取主程序可能使用的 Logger
logger = logging.getLogger("WVD")

try:
    import websockets
    from websockets.server import serve
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


def _get_resource_base_dir():
    """
    智慧取得 resources 資料夾的根目錄。
    - 打包環境 (PyInstaller): 使用 _internal 目錄 (sys._MEIPASS)
    - 開發環境: 使用 src/../ (專案根目錄)
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包環境: _internal 目錄
        # sys._MEIPASS 直接指向 _internal
        return sys._MEIPASS
    else:
        # 開發環境: src 的上一層
        return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))



# -----------------------------------------------------------------------------
# Custom Compact JSON Formatter
# 用於保持 Quest JSON 的緊湊格式 (例如 list 不會強制換行)
# -----------------------------------------------------------------------------
def _is_compactable(data):
    """
    判斷一個 list 是否適合壓縮成單行。
    條件：
    1. 不包含 dict (dict 通常需要換行)
    2. 遞歸檢查子 list
    """
    if not isinstance(data, list):
        return True # Primitives are compact
        
    for item in data:
        if isinstance(item, dict):
            return False
        if isinstance(item, list):
            if not _is_compactable(item):
                return False
    return True

def _format_json(data, indent=0):
    """
    遞歸格式化 JSON，對於符合條件的 list 強制單行顯示。
    """
    pad = " " * indent
    if isinstance(data, dict):
        if not data: return "{}"
        
        # 為了美觀，Dictionary 總是換行
        items = []
        items.append("{\n")
        keys = list(data.keys())
        for i, k in enumerate(keys):
            v = data[k]
            comma = "," if i < len(keys) - 1 else ""
            
            k_str = json.dumps(k, ensure_ascii=False)
            
            # 遞歸獲取值 (增加縮進)
            v_str = _format_json(v, indent + 4)
            
            # 處理值的縮進 (如果是 Compact List，則 v_str 已經是字串; 如果是結構，則 v_str 第一行有縮進)
            # 我們希望形式為: "key": value
            # 如果 value 是多行結構，其第一行縮進應該被忽略 (接在 key 後面)，後續行保持縮進
            
            items.append(f"{pad}    {k_str}: {v_str.lstrip()}{comma}\n")
            
        items.append(f"{pad}}}")
        return "".join(items)
        
    elif isinstance(data, list):
        if not data: return "[]"
        
        # 檢查是否可以緊湊顯示
        # 1. 結構簡單 (無 Dict)
        # 2. 長度適中 (避免極長的一行)
        if _is_compactable(data):
             compact_str = json.dumps(data, ensure_ascii=False)
             # 限制單行最大長度，超過則展開 (例如 _EOT 有些很長)
             if len(compact_str) < 120:
                 return f"{pad}{compact_str}"
        
        # 展開顯示
        items = []
        items.append(f"{pad}[\n")
        for i, item in enumerate(data):
            comma = "," if i < len(data) - 1 else ""
            v_str = _format_json(item, indent + 4)
            items.append(f"{v_str}{comma}\n")
        items.append(f"{pad}]")
        return "".join(items)
        
    else:
        # 基本型別 (str, int, float, bool, None)
        return f"{pad}{json.dumps(data, ensure_ascii=False)}"


class EditorWebSocketServer:
    def __init__(self, host="localhost", port=8765, quest_json_path=None):
        self.host = host
        self.port = port
        self.quest_json_path = quest_json_path or os.path.join(
            _get_resource_base_dir(), "resources", "quest", "quest.json"
        )
        self.clients = set()
        self.running = False
        self._adb_device = None
        self._get_frame_func = None
        self.stream_fps = 10  # 稍微降低 FPS 提高指令穩定性
        self.jpeg_quality = 50

    def _transform_quest_rois(self, data, mode='to_script'):
        """
        遞歸遍歷任務資料，轉換 ROI 格式
        mode='to_editor': [x, y, w, h] -> [x, y, x+w, y+h]
        mode='to_script': [x, y, x2, y2] -> [x, y, x2-x, y2-y]
        """
        if not isinstance(data, (dict, list)):
            return data

        if isinstance(data, dict):
            # 如果是任務對象，遍歷其內容
            for k, v in data.items():
                if k == "_TARGETINFOLIST" and isinstance(v, list):
                    for target_item in v:
                        # target_item 格式: [target_name, swipe_dir, roi_list]
                        if len(target_item) >= 3 and isinstance(target_item[2], list):
                            new_rois = []
                            for rect in target_item[2]:
                                if isinstance(rect, list) and len(rect) == 4:
                                    x, y, val3, val4 = rect
                                    if mode == 'to_editor':
                                        # 只有看起來是寬高格式時才轉換 (val3+x <= 900)
                                        if x + val3 <= 905 and y + val4 <= 1605:
                                            new_rois.append([x, y, x + val3, y + val4])
                                        else:
                                            new_rois.append(rect)
                                    else: # to_script
                                        # 只有看起來是坐標格式時才轉換 (val3 > x)
                                        if val3 >= x and val4 >= y and (x + val3 > 900 or y + val4 > 1600):
                                            new_rois.append([x, y, val3 - x, val4 - y])
                                        else:
                                            new_rois.append(rect)
                                else:
                                    new_rois.append(rect)
                            target_item[2] = new_rois
                else:
                    self._transform_quest_rois(v, mode)
        elif isinstance(data, list):
            for item in data:
                self._transform_quest_rois(item, mode)

    def start(self):
        if not WEBSOCKETS_AVAILABLE:
            print("[EditorServer] ❌ 尚未安裝 websockets 套件，無法啟動編輯器伺服器。請執行 pip install websockets")
            return False
            
        if self.running: return True
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()
        # 等待啟動
        for _ in range(30):
            if self.running: return True
            time.sleep(0.1)
        return False

    def _run_event_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._start_server_internal())
            # NOTE: running 已在 _start_server_internal 中設置
            print(f"\n[EditorServer] 伺服器已在 ws://{self.host}:{self.port} 啟動")
            sys.stdout.flush()
            self._loop.run_forever()
        except Exception as e:
            print(f"[EditorServer] 事件循環崩潰: {e}")
        finally:
            self._loop.close()

    async def _start_server_internal(self):
        self._server = await serve(
            self._connection_handler, 
            self.host, 
            self.port,
            ping_interval=20, # 每 20 秒發送一次 ping
            ping_timeout=20   # 如果 20 秒沒收到 pong 則判定斷線
        )
        # NOTE: 必須在創建串流任務前設置 running，否則 while self.running 會立即退出
        self.running = True
        self._stream_task = asyncio.create_task(self._stream_broadcast_loop())

    async def _connection_handler(self, websocket):
        self.clients.add(websocket)
        msg = f"[EditorServer] 客戶端連線: {websocket.remote_address}"
        print(msg)
        sys.stdout.flush()
        logger.info(msg)
        
        try:
            async for message in websocket:
                if isinstance(message, str):
                    # 收到指令立即列印到終端
                    print(f"[EditorServer] 收到指令: {message}")
                    sys.stdout.flush()
                    logger.info(f"[EditorServer] 指令: {message}")
                    await self._process_command(websocket, message)
        except Exception as e:
            print(f"[EditorServer] 連線異常: {e}")
        finally:
            self.clients.remove(websocket)
            print(f"[EditorServer] 客戶端中斷: {websocket.remote_address}")
            sys.stdout.flush()

    async def _process_command(self, websocket, message):
        try:
            # ADB 直接指令
            if message.startswith("input "):
                # 方案 A: 使用已注入的 ppadb 設備對象 (最推薦)
                if self._adb_device:
                    try:
                        # ppadb 的 shell 不需要 "adb shell" 前綴，只需要後面的指令
                        print(f"[EditorServer] 透過 ppadb 執行: {message}")
                        self._adb_device.shell(message)
                        return
                    except Exception as e:
                        print(f"[EditorServer] ppadb 執行失敗: {e}")

                # 方案 B: 使用 subprocess (備用)
                import subprocess
                # 嘗試檢測 MuMu 的 ADB 路徑
                adb_exe = "adb"
                mumu_adb = r"C:\Program Files\Netease\MuMuPlayer\nx_device\12.0\shell\adb.exe"
                if os.path.exists(mumu_adb):
                    adb_exe = f'"{mumu_adb}"'
                
                print(f"[EditorServer] 透過 subprocess 執行: {adb_exe} shell {message}")
                subprocess.Popen(f"{adb_exe} shell {message}", shell=True)
                return

            # JSON 指令
            data = json.loads(message)
            cmd = data.get("cmd")
            if cmd == "load_quest":
                await self._handle_load_quest(websocket)
            elif cmd == "save_quest":
                await self._handle_save_quest(websocket, data.get("data"))
            elif cmd == "save_image":
                await self._handle_save_image(websocket, data.get("filename"), data.get("data"), data.get("captureTarget"))
            elif cmd == "click_image":
                await self._handle_click_image(websocket, data.get("filename"))
            elif cmd == "list_images":
                await self._handle_list_images(websocket)
            elif cmd == "get_image":
                await self._handle_get_image(websocket, data.get("filename"))
        except Exception as e:
            print(f"[EditorServer] 處理指令出錯: {e}")

    # ... (原有 stream loop 和其他 handler) ...

    async def _handle_click_image(self, websocket, filename):
        if not CV2_AVAILABLE:
            await websocket.send(json.dumps({"type": "log", "message": "❌ 伺服器缺少 OpenCV，無法進行圖片比對"}))
            return
            
        if not self._get_frame_func:
            await websocket.send(json.dumps({"type": "log", "message": "❌ 無法獲取當前畫面串流"}))
            return

        try:
            # 1. 獲取當前畫面
            screen = self._get_frame_func()
            if screen is None:
                await websocket.send(json.dumps({"type": "log", "message": "❌ 當前畫面為空"}))
                return

            # 2. 讀取目標圖片
            # 從 images 根目錄開始搜尋，支援 userscript/XXX 或 character/XXX 等子目錄
            base_dir = os.path.join(_get_resource_base_dir(), "resources", "images")
            # 支援子目錄 (e.g. userscript/AWD 或 character/return)
            target_path = os.path.join(base_dir, filename)
            
            # 如果沒有副檔名，嘗試加上 .png
            if not os.path.exists(target_path) and not target_path.lower().endswith(".png"):
                target_path += ".png"
            
            # Debug: 印出絕對路徑
            abs_path = os.path.abspath(target_path)
            print(f"[EditorServer] 正在尋找圖片: {abs_path}")
                
            if not os.path.exists(target_path):
                 msg = f"❌ 找不到圖片檔案: {filename} (路徑: {abs_path})"
                 print(f"[EditorServer] {msg}")
                 await websocket.send(json.dumps({"type": "log", "message": msg}))
                 return

            # 3. 讀圖並進行模板匹配
            # 必須使用 IMREAD_UNCHANGED 讀取可能帶有透明通道的圖，或者直接 IMREAD_COLOR
            # 這裡假設都是彩色比對
            template = cv2.imread(target_path, cv2.IMREAD_COLOR)
            if template is None:
                await websocket.send(json.dumps({"type": "log", "message": f"❌ 圖片讀取失敗: {filename}"}))
                return

            # 確保 screen 也是彩色 (如果串流是灰階需要轉換，但通常是 BGR)
            # 進行匹配
            res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            
            threshold = 0.8
            if max_val >= threshold:
                # 4. 計算中心點並點擊
                h, w = template.shape[:2]
                center_x = max_loc[0] + w // 2
                center_y = max_loc[1] + h // 2
                
                msg = f"✅ 找到圖片 '{filename}' (相似度: {max_val:.2f}) @ ({center_x}, {center_y})"
                print(f"[EditorServer] {msg}")
                await websocket.send(json.dumps({"type": "log", "message": msg}))
                
                # 執行點擊
                cmd = f"input tap {center_x} {center_y}"
                
                # 復用上面的 ADB 執行邏輯 (這裡簡單 copy，理想應重構為方法)
                if self._adb_device:
                    self._adb_device.shell(cmd)
                else:
                    import subprocess
                    adb_exe = "adb"
                    mumu_adb = r"C:\Program Files\Netease\MuMuPlayer\nx_device\12.0\shell\adb.exe"
                    if os.path.exists(mumu_adb): adb_exe = f'"{mumu_adb}"'
                    subprocess.Popen(f"{adb_exe} shell {cmd}", shell=True)
                    
            else:
                msg = f"⚠ 未找到圖片 '{filename}' (最高相似度: {max_val:.2f})"
                print(f"[EditorServer] {msg}")
                await websocket.send(json.dumps({"type": "log", "message": msg}))

        except Exception as e:
            print(f"[EditorServer] 圖片比對出錯: {e}")
            await websocket.send(json.dumps({"type": "log", "message": f"❌ 比對出錯: {e}"}))

    async def _stream_broadcast_loop(self):
        # NOTE: 此循環需要在 running=False 時正確退出，否則 stop() 會阻塞
        try:
            while self.running:
                await asyncio.sleep(1.0 / self.stream_fps)
                if not self.clients:
                    continue
                
                frame = None
                if self._get_frame_func:
                    frame = self._get_frame_func()
                    
                if frame is not None and CV2_AVAILABLE:
                    try:
                        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
                        jpg_as_text = buffer.tobytes()
                        # 廣播
                        tasks = [client.send(jpg_as_text) for client in self.clients]
                        await asyncio.gather(*tasks, return_exceptions=True)
                    except Exception as e:
                        pass
        except asyncio.CancelledError:
            # 正常取消，不需要輸出錯誤
            pass
        print("[EditorServer] 串流循環已停止")

    async def _handle_load_quest(self, websocket):
        try:
            with open(self.quest_json_path, "r", encoding="utf-8") as f:
                content = json.load(f)
            
            # 轉換為編輯器使用的格式 (x2, y2)
            self._transform_quest_rois(content, 'to_editor')
            
            await websocket.send(json.dumps({"type": "quest", "data": content}))
        except Exception as e:
            await websocket.send(json.dumps({"type": "error", "message": f"載入失敗: {e}"}))

    async def _handle_save_quest(self, websocket, data):
        try:
            abs_path = os.path.abspath(self.quest_json_path)
            
            logger.info(f"[EditorServer] 收到保存請求。包含 {len(data)} 個任務。")

            # 轉換為腳本使用的格式 (w, h)
            self._transform_quest_rois(data, 'to_script')

            # 使用自定義的緊湊格式保存
            json_str = _format_json(data)
            
            with open(self.quest_json_path, "w", encoding="utf-8") as f:
                f.write(json_str)
                
            await websocket.send(json.dumps({"type": "saved", "success": True, "path": abs_path}))
            logger.info(f"[EditorServer] quest.json 儲存成功 (ROI 自動校正並以 Compact Mode 儲存): {abs_path}")
        except Exception as e:
            logger.error(f"[EditorServer] 儲存失敗 ERROR: {e}")
            await websocket.send(json.dumps({"type": "error", "message": f"儲存失敗: {e}"}))



    async def _handle_save_image(self, websocket, filename, base64_data, capture_target=None):
        try:
            import base64
            img_data = base64.b64decode(base64_data)
            
            # 決定儲存路徑
            # images 根目錄
            base_dir = os.path.join(_get_resource_base_dir(), "resources", "images")
            
            # 去除 .png
            if filename.lower().endswith('.png'):
                clean_name = filename[:-4]
            else:
                clean_name = filename
                
            # 檢查是否有目錄結構 (e.g. AWD/image)
            if "/" in clean_name or "\\" in clean_name:
                # 使用者指定了子目錄
                rel_path = clean_name
            else:
                # 預設存到 userscript 子目錄
                rel_path = f"userscript/{clean_name}"
            
            # 最終絕對路徑
            final_path = os.path.join(base_dir, rel_path + ".png")
            os.makedirs(os.path.dirname(final_path), exist_ok=True)
            
            with open(final_path, "wb") as f:
                f.write(img_data)
                
            # 回傳給前端的檔名應該包含相對路徑 (e.g. userscript/myimg.png)
            final_rel_name = rel_path
            
            await websocket.send(json.dumps({
                "type": "image_saved",
                "success": True,
                "filename": final_rel_name,
                "captureTarget": capture_target
            }))
            print(f"[EditorServer] 圖片已存至: {final_path}")
        except Exception as e:
            await websocket.send(json.dumps({"type": "error", "message": f"存圖失敗: {e}"}))

    async def _handle_list_images(self, websocket):
        try:
            base_dir = os.path.join(_get_resource_base_dir(), "resources", "images")
            images = []
            
            for root, dirs, files in os.walk(base_dir):
                for file in files:
                    if file.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                        # 取得相對路徑
                        rel_path = os.path.relpath(os.path.join(root, file), base_dir)
                        # 統一使用正斜線
                        rel_path = rel_path.replace("\\", "/")
                        
                        # 忽略某些不需要顯示的系統圖片(Optional)
                        # if "system" in rel_path: continue
                        
                        # 為了前端顯示方便，我們可以選擇是否去掉 .png，
                        # 但如果要用於 input value，最好保持完整或與 save 邏輯一致。
                        # 目前保留完整路徑 (e.g. "userscript/myimg.png")
                        # 這樣前端拿到也可以直接做 check
                        images.append(rel_path)
            
            # Sort
            images.sort()
            
            await websocket.send(json.dumps({"type": "image_list", "images": images}))
            print(f"[EditorServer] 已回傳 {len(images)} 張圖片")
        except Exception as e:
            await websocket.send(json.dumps({"type": "error", "message": f"列表失敗: {e}"}))

    async def _handle_get_image(self, websocket, filename):
        try:
            import base64
            # 圖片根目錄
            base_dir = os.path.join(_get_resource_base_dir(), "resources", "images")
            
            # 組合路徑
            # filename 可能包含子目錄 (e.g. userscript/myimg.png)
            target_path = os.path.join(base_dir, filename)
            
            if not os.path.exists(target_path):
                 # 嘗試加 .png
                 if os.path.exists(target_path + ".png"):
                     target_path += ".png"
                 else:
                     await websocket.send(json.dumps({"type": "error", "message": f"找不到圖片: {filename}"}))
                     return
            
            with open(target_path, "rb") as f:
                img_bytes = f.read()
                b64_str = base64.b64encode(img_bytes).decode('utf-8')
                
            await websocket.send(json.dumps({
                "type": "image_data", 
                "filename": filename,
                "data": b64_str
            }))
            print(f"[EditorServer] 已傳送圖片預覽: {filename}")
            
        except Exception as e:
            await websocket.send(json.dumps({"type": "error", "message": f"讀圖失敗: {e}"}))

    def set_stream_source(self, func):
        self._get_frame_func = func

    def stop(self):
        """優雅停止 WebSocket 伺服器"""
        if not self.running:
            return
        
        print("[EditorServer] 正在停止伺服器...")
        self.running = False
        
        if hasattr(self, "_loop") and self._loop.is_running():
            # 在事件循環中執行關閉操作
            async def _shutdown():
                # 1. 取消串流任務
                if hasattr(self, "_stream_task") and not self._stream_task.done():
                    self._stream_task.cancel()
                    try:
                        await self._stream_task
                    except asyncio.CancelledError:
                        pass  # 正常取消
                
                # 2. 關閉 WebSocket 伺服器，停止接受新連線
                if hasattr(self, "_server"):
                    self._server.close()
                    await self._server.wait_closed()
                
                # 3. 中斷所有現有客戶端連線
                if self.clients:
                    for client in list(self.clients):
                        try:
                            await client.close()
                        except Exception:
                            pass
                    self.clients.clear()
                
                # 4. 停止事件循環
                self._loop.stop()
            
            self._loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(_shutdown(), loop=self._loop)
            )
        
        # 等待執行緒結束（最多 3 秒）
        if hasattr(self, "_thread") and self._thread.is_alive():
            self._thread.join(timeout=3.0)
            if self._thread.is_alive():
                print("[EditorServer] ⚠ 執行緒未能在時限內結束")
        
        print("[EditorServer] 伺服器已停止")

_server_instance = None

def start_editor_server(adb_port=None, stream_func=None):
    global _server_instance
    if _server_instance and _server_instance.running: return True
    _server_instance = EditorWebSocketServer()
    if stream_func: _server_instance.set_stream_source(stream_func)
    return _server_instance.start()

def stop_editor_server():
    global _server_instance
    if _server_instance:
        _server_instance.stop()
        _server_instance = None
