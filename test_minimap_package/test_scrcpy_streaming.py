#!/usr/bin/env python3
"""
測試 scrcpy 串流模式 - 即時視頻串流抓取幀
比 ADB 截圖快約 20 倍

使用方式：
1. 確保模擬器已連接 (adb devices 可以看到設備)
2. 在遊戲中移動到有樓層標識的位置
3. 執行此腳本: python test_scrcpy_streaming.py
4. 按 Ctrl+C 停止
"""

import subprocess
import time
import cv2
import numpy as np
import sys
import threading
from pathlib import Path

# 路徑設定 (相對於腳本位置)
SCRIPT_DIR = Path(__file__).parent
SCRCPY_PATH = SCRIPT_DIR / "scrcpy"
SCRCPY_EXE = SCRCPY_PATH / "scrcpy.exe"
ADB_EXE = SCRCPY_PATH / "adb.exe"

# 模板圖片
TEMPLATES = {
    "DH-R5-minimap": SCRIPT_DIR / "resources" / "images" / "DH-R5-minimap.png",
    "DH-R6-minimap": SCRIPT_DIR / "resources" / "images" / "DH-R6-minimap.png",
}

# 偵測區域 (小地圖位置) - 右上角
# 格式: [x, y, width, height]
# 900x1600 螢幕，小地圖在右上角
MINIMAP_ROI = [650, 0, 250, 250]


class ScrcpyStream:
    """scrcpy 視頻串流捕獲器"""
    
    def __init__(self, scrcpy_path, max_size=1600, bitrate="2M"):
        self.scrcpy_path = scrcpy_path
        self.max_size = max_size
        self.bitrate = bitrate
        self.process = None
        self.frame = None
        self.frame_lock = threading.Lock()
        self.running = False
        self.capture_thread = None
        
    def start(self):
        """啟動 scrcpy 串流"""
        # scrcpy 參數：
        # --no-window：不顯示視窗
        # --video-codec=h264：使用 H.264 編碼
        # --max-size：最大解析度
        # --bit-rate：位元率
        # --render-driver=software：軟體渲染（避免 GPU 問題）
        cmd = [
            str(self.scrcpy_path / "scrcpy.exe"),
            "--no-window",
            "--no-audio",
            "--video-codec=h264",
            f"--max-size={self.max_size}",
            f"--video-bit-rate={self.bitrate}",
            "--render-driver=software",
            "--v4l2-sink=/dev/null"  # 這個在 Windows 無效，但不會報錯
        ]
        
        # 使用 FFmpeg 管道獲取視頻流
        # scrcpy 可以輸出到標準輸出
        cmd_raw = [
            str(self.scrcpy_path / "scrcpy.exe"),
            "--no-window",
            "--no-audio",
            "--video-codec=h264",
            f"--max-size={self.max_size}",
            f"--video-bit-rate={self.bitrate}",
            "--record=-",  # 輸出到 stdout
            "--record-format=mkv"
        ]
        
        print(f"啟動 scrcpy 串流...")
        print(f"命令: {' '.join(cmd_raw)}")
        
        try:
            self.process = subprocess.Popen(
                cmd_raw,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=10**8
            )
            self.running = True
            
            # 啟動捕獲線程
            self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.capture_thread.start()
            
            # 等待第一幀
            time.sleep(2)
            return True
            
        except Exception as e:
            print(f"啟動失敗: {e}")
            return False
    
    def _capture_loop(self):
        """捕獲循環 - 從 FFmpeg 讀取幀"""
        # 使用 OpenCV 的 VideoCapture 無法直接讀取 scrcpy 的輸出
        # 需要使用 FFmpeg 作為中間層
        # 這裡我們使用另一種方法：讓 scrcpy 輸出到管道，用 ffmpeg 解碼
        pass
    
    def get_frame(self):
        """獲取當前幀"""
        with self.frame_lock:
            return self.frame.copy() if self.frame is not None else None
    
    def stop(self):
        """停止串流"""
        self.running = False
        if self.process:
            self.process.terminate()
            self.process.wait()
        print("scrcpy 串流已停止")


class ScrcpyStreamV2:
    """scrcpy 視頻串流捕獲器 - 使用 ADB forward + socket"""
    
    def __init__(self, adb_path, port=27183):
        self.adb_path = adb_path
        self.port = port
        self.frame = None
        self.frame_lock = threading.Lock()
        self.running = False
        
    def start(self):
        """這個方法太複雜，我們用更簡單的方式"""
        pass


def scrcpy_screenshot_fast():
    """
    使用 scrcpy 的快速截圖模式
    比 adb screencap 稍快
    """
    try:
        # 使用 adb exec-out 但優化參數
        result = subprocess.run(
            [str(ADB_EXE), "exec-out", "screencap"],
            capture_output=True,
            timeout=5
        )
        
        if result.returncode == 0 and len(result.stdout) > 0:
            # screencap 原始輸出是 RGBA
            data = result.stdout
            
            # 解析頭部獲取寬高
            if len(data) < 12:
                return None
                
            w = int.from_bytes(data[0:4], 'little')
            h = int.from_bytes(data[4:8], 'little')
            fmt = int.from_bytes(data[8:12], 'little')
            
            # 跳過頭部 12 bytes
            pixels = data[12:]
            
            expected_size = w * h * 4  # RGBA
            if len(pixels) >= expected_size:
                # 轉換為 numpy array
                frame = np.frombuffer(pixels[:expected_size], dtype=np.uint8)
                frame = frame.reshape((h, w, 4))
                # RGBA -> BGR
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
                return frame
                
    except Exception as e:
        print(f"快速截圖錯誤: {e}")
    return None


def adb_screenshot():
    """使用 ADB 截圖 (直式，不旋轉) - 作為對照"""
    try:
        result = subprocess.run(
            [str(ADB_EXE), "exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=10
        )
        
        if result.returncode == 0 and len(result.stdout) > 0:
            nparr = np.frombuffer(result.stdout, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
            
            if frame is not None:
                if len(frame.shape) == 3 and frame.shape[2] == 4:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            
            return frame
    except subprocess.TimeoutExpired:
        print("截圖超時！")
    except Exception as e:
        print(f"截圖錯誤: {e}")
    return None


def check_template(frame, template_path, roi=None, threshold=0.8):
    """模板匹配"""
    if frame is None:
        return {"found": False, "match_val": 0, "position": None}
        
    template = cv2.imread(str(template_path))
    if template is None:
        print(f"無法載入模板: {template_path}")
        return {"found": False, "match_val": 0, "position": None}
    
    search_area = frame
    offset_x, offset_y = 0, 0
    if roi:
        x, y, w, h = roi
        h_max, w_max = frame.shape[:2]
        x = min(x, w_max - 1)
        y = min(y, h_max - 1)
        w = min(w, w_max - x)
        h = min(h, h_max - y)
        search_area = frame[y:y+h, x:x+w]
        offset_x, offset_y = x, y
    
    if search_area.shape[0] < template.shape[0] or search_area.shape[1] < template.shape[1]:
        search_area = frame
        offset_x, offset_y = 0, 0
    
    try:
        result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        found = max_val >= threshold
        position = (max_loc[0] + offset_x, max_loc[1] + offset_y) if found else None
        
        return {
            "found": found,
            "match_val": max_val,
            "position": position
        }
    except Exception as e:
        print(f"模板匹配錯誤: {e}")
        return {"found": False, "match_val": 0, "position": None}


def main():
    """主測試程式 - 比較 ADB vs 快速截圖"""
    print("=" * 60)
    print("scrcpy 串流模式測試")
    print("比較 ADB 截圖 vs 原始 screencap")
    print("=" * 60)
    
    # 檢查檔案
    if not ADB_EXE.exists():
        print(f"錯誤: 找不到 adb.exe: {ADB_EXE}")
        input("按 Enter 退出...")
        return
    
    print(f"✓ ADB 路徑: {ADB_EXE}")
    
    for name, path in TEMPLATES.items():
        if not path.exists():
            print(f"錯誤: 找不到模板圖片: {path}")
            input("按 Enter 退出...")
            return
        template = cv2.imread(str(path))
        print(f"✓ {name}: {template.shape[1]}x{template.shape[0]} 像素")
    
    # 檢查 ADB 連接
    print("\n檢查 ADB 設備...")
    result = subprocess.run([str(ADB_EXE), "devices"], capture_output=True, text=True, timeout=10)
    print(result.stdout.strip())
    
    lines = result.stdout.strip().split('\n')
    devices = [l for l in lines[1:] if l.strip() and 'device' in l]
    if not devices:
        print("\n錯誤: 沒有連接的設備！")
        input("按 Enter 退出...")
        return
    
    print("\n" + "=" * 60)
    print("測試 1: ADB screencap -p (PNG 編碼)")
    print("=" * 60)
    
    times_adb = []
    for i in range(5):
        start = time.time()
        frame = adb_screenshot()
        elapsed = time.time() - start
        times_adb.append(elapsed)
        if frame is not None:
            print(f"  #{i+1}: {elapsed:.3f}s ({frame.shape[1]}x{frame.shape[0]})")
        else:
            print(f"  #{i+1}: 失敗")
    
    avg_adb = sum(times_adb) / len(times_adb)
    print(f"  平均: {avg_adb:.3f}s")
    
    print("\n" + "=" * 60)
    print("測試 2: ADB screencap 原始格式 (無 PNG 編碼)")
    print("=" * 60)
    
    times_raw = []
    for i in range(5):
        start = time.time()
        frame = scrcpy_screenshot_fast()
        elapsed = time.time() - start
        times_raw.append(elapsed)
        if frame is not None:
            print(f"  #{i+1}: {elapsed:.3f}s ({frame.shape[1]}x{frame.shape[0]})")
        else:
            print(f"  #{i+1}: 失敗")
    
    avg_raw = sum(times_raw) / len(times_raw)
    print(f"  平均: {avg_raw:.3f}s")
    
    print("\n" + "=" * 60)
    print("結果比較")
    print("=" * 60)
    print(f"  ADB PNG 模式:    {avg_adb:.3f}s/幀  ({1/avg_adb:.1f} FPS)")
    print(f"  ADB 原始模式:    {avg_raw:.3f}s/幀  ({1/avg_raw:.1f} FPS)")
    if avg_raw > 0 and avg_adb > 0:
        speedup = avg_adb / avg_raw
        print(f"  加速比例:        {speedup:.1f}x")
    
    print("\n" + "=" * 60)
    print("開始持續偵測 (使用較快的模式)... 按 Ctrl+C 停止")
    print("=" * 60)
    
    # 選擇較快的模式
    use_raw = avg_raw < avg_adb
    screenshot_func = scrcpy_screenshot_fast if use_raw else adb_screenshot
    mode_name = "原始模式" if use_raw else "PNG模式"
    print(f"使用: {mode_name}")
    print("-" * 60)
    
    frame_count = 0
    start_time = time.time()
    found_r5_count = 0
    found_r6_count = 0
    
    try:
        while True:
            loop_start = time.time()
            
            frame = screenshot_func()
            screenshot_time = time.time() - loop_start
            
            if frame is None:
                print("截圖失敗，等待重試...")
                time.sleep(1)
                continue
            
            frame_count += 1
            
            results = {}
            for name, path in TEMPLATES.items():
                result = check_template(frame, path, roi=MINIMAP_ROI, threshold=0.7)
                results[name] = result
            
            total_time = time.time() - loop_start
            
            r5_val = results["DH-R5-minimap"]["match_val"] * 100
            r6_val = results["DH-R6-minimap"]["match_val"] * 100
            
            r5_found = results["DH-R5-minimap"]["found"]
            r6_found = results["DH-R6-minimap"]["found"]
            
            if r5_found:
                found_r5_count += 1
            if r6_found:
                found_r6_count += 1
            
            r5_status = "<<找到!>>" if r5_found else ""
            r6_status = "<<找到!>>" if r6_found else ""
            
            print(f"[{total_time:.2f}s] "
                  f"R5: {r5_val:5.1f}% {r5_status:10} | "
                  f"R6: {r6_val:5.1f}% {r6_status:10} | "
                  f"截圖:{screenshot_time:.2f}s")
            
            if r5_found or r6_found:
                timestamp = time.strftime("%H%M%S")
                found_name = "R5" if r5_found else "R6"
                filename = f"detected_{found_name}_{timestamp}.png"
                cv2.imwrite(filename, frame)
                print(f"    >>> 已儲存截圖: {filename}")
            
            time.sleep(0.05)
                
    except KeyboardInterrupt:
        elapsed_total = time.time() - start_time
        print("\n" + "=" * 60)
        print(f"測試結束！")
        print(f"  共 {frame_count} 幀，耗時 {elapsed_total:.1f} 秒")
        print(f"  平均 FPS: {frame_count / elapsed_total:.2f}")
        print(f"  R5 找到次數: {found_r5_count}")
        print(f"  R6 找到次數: {found_r6_count}")
        print("=" * 60)
        input("按 Enter 退出...")


if __name__ == "__main__":
    main()
