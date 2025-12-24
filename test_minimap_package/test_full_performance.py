#!/usr/bin/env python3
"""
完整效能測試 - 使用 pyscrcpy 進行視頻串流

測試項目:
1. ADB screencap -p (PNG 編碼)
2. ADB screencap 原始格式
3. pyscrcpy 視頻串流

需要:
- opencv-python
- numpy
- pyscrcpy
- av (PyAV)

安裝:
pip install pyscrcpy av opencv-python numpy

使用方式:
python test_full_performance.py
"""

import subprocess
import time
import cv2
import numpy as np
import threading
import sys
import os
from pathlib import Path

# 檢查 pyscrcpy
try:
    from pyscrcpy import Client as ScrcpyClient
    PYSCRCPY_AVAILABLE = True
    print("✓ pyscrcpy 已安裝")
except ImportError:
    PYSCRCPY_AVAILABLE = False
    ScrcpyClient = None
    print("✗ pyscrcpy 未安裝 (pip install pyscrcpy)")

# 路徑設定 - 支援 PyInstaller 打包
if getattr(sys, 'frozen', False):
    # 打包後的執行檔，使用執行檔所在目錄
    SCRIPT_DIR = Path(sys.executable).parent
else:
    # 普通 Python 腳本
    SCRIPT_DIR = Path(__file__).parent

SCRCPY_PATH = SCRIPT_DIR / "scrcpy"
ADB_EXE = SCRCPY_PATH / "adb.exe"

# 模板圖片
TEMPLATES = {
    "DH-R5-minimap": SCRIPT_DIR / "resources" / "images" / "DH-R5-minimap.png",
    "DH-R6-minimap": SCRIPT_DIR / "resources" / "images" / "DH-R6-minimap.png",
}

MINIMAP_ROI = [650, 0, 250, 250]


class PyscrcpyStream:
    """使用 pyscrcpy 進行視頻串流"""
    
    def __init__(self, max_fps=60, bitrate=8000000, max_size=1600):
        self.max_fps = max_fps
        self.bitrate = bitrate
        self.max_size = max_size
        
        self.client = None
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.frame_count = 0
        self.running = False
        self.reader_thread = None
        
    def _on_frame(self, client, frame):
        """幀回調"""
        if frame is not None:
            with self.frame_lock:
                # pyscrcpy 返回的是 numpy array (BGR)
                self.latest_frame = frame.copy()
                self.frame_count += 1
    
    def _frame_reader(self):
        """從 last_frame 讀取幀"""
        while self.running:
            if self.client and self.client.last_frame is not None:
                with self.frame_lock:
                    self.latest_frame = self.client.last_frame.copy()
                    self.frame_count += 1
            time.sleep(0.01)  # 10ms 間隔
    
    def start(self):
        """啟動串流"""
        if not PYSCRCPY_AVAILABLE:
            print("錯誤: 需要安裝 pyscrcpy (pip install pyscrcpy)")
            return False
        
        try:
            print(f"啟動 pyscrcpy 串流...")
            print(f"  max_fps={self.max_fps}, max_size={self.max_size}")
            
            # 創建 scrcpy client
            self.client = ScrcpyClient(
                max_fps=self.max_fps,
                max_size=self.max_size,
            )
            
            # 設置幀回調
            self.client.on_frame(self._on_frame)
            
            # 啟動 (非阻塞線程模式)
            self.client.start(threaded=True)
            
            self.running = True
            
            # 等待第一幀
            for i in range(100):  # 最多等 10 秒
                if self.client.last_frame is not None:
                    with self.frame_lock:
                        self.latest_frame = self.client.last_frame.copy()
                        self.frame_count += 1
                    print(f"✓ 串流已啟動！")
                    return True
                time.sleep(0.1)
            
            print("超時：沒有收到幀")
            return False
            
        except Exception as e:
            print(f"啟動失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_frame(self):
        """獲取最新幀"""
        if self.client and self.client.last_frame is not None:
            return self.client.last_frame.copy()
        return None
    
    def stop(self):
        """停止串流"""
        self.running = False
        if self.client:
            try:
                self.client.stop()
            except:
                pass
        print("串流已停止")


def adb_screenshot_png():
    """ADB 截圖 - PNG 格式"""
    try:
        result = subprocess.run(
            [str(ADB_EXE), "exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=10
        )
        
        if result.returncode == 0 and len(result.stdout) > 0:
            nparr = np.frombuffer(result.stdout, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
            if frame is not None and len(frame.shape) == 3 and frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            return frame
    except:
        pass
    return None


def adb_screenshot_raw():
    """ADB 截圖 - 原始格式"""
    try:
        result = subprocess.run(
            [str(ADB_EXE), "exec-out", "screencap"],
            capture_output=True,
            timeout=5
        )
        
        if result.returncode == 0 and len(result.stdout) > 12:
            data = result.stdout
            w = int.from_bytes(data[0:4], 'little')
            h = int.from_bytes(data[4:8], 'little')
            
            pixels = data[12:]
            expected_size = w * h * 4
            
            if len(pixels) >= expected_size:
                frame = np.frombuffer(pixels[:expected_size], dtype=np.uint8)
                frame = frame.reshape((h, w, 4))
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
                return frame
    except:
        pass
    return None


def check_template(frame, template_path, roi=None, threshold=0.8):
    """模板匹配"""
    if frame is None:
        return {"found": False, "match_val": 0}
        
    template = cv2.imread(str(template_path))
    if template is None:
        return {"found": False, "match_val": 0}
    
    search_area = frame
    if roi:
        x, y, w, h = roi
        h_max, w_max = frame.shape[:2]
        x, y = min(x, w_max-1), min(y, h_max-1)
        w, h = min(w, w_max-x), min(h, h_max-y)
        search_area = frame[y:y+h, x:x+w]
    
    if search_area.shape[0] < template.shape[0] or search_area.shape[1] < template.shape[1]:
        search_area = frame
    
    try:
        result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
        return {"found": max_val >= threshold, "match_val": max_val}
    except:
        return {"found": False, "match_val": 0}


def benchmark_method(name, get_frame_func, iterations=20):
    """測試效能"""
    print(f"\n{'='*60}")
    print(f"測試: {name}")
    print(f"{'='*60}")
    
    times = []
    success = 0
    
    for i in range(iterations):
        start = time.time()
        frame = get_frame_func()
        elapsed = time.time() - start
        
        if frame is not None:
            times.append(elapsed)
            success += 1
            
            r5 = check_template(frame, TEMPLATES["DH-R5-minimap"], MINIMAP_ROI)
            found_mark = "<<找到!>>" if r5["found"] else ""
            print(f"  #{i+1:2d}: {elapsed*1000:6.1f}ms  R5:{r5['match_val']*100:5.1f}% {found_mark}")
        else:
            print(f"  #{i+1:2d}: 失敗")
    
    if times:
        avg = sum(times) / len(times)
        return {"avg": avg, "min": min(times), "max": max(times), 
                "fps": 1/avg, "success": success/iterations}
    return None


def main():
    print("=" * 60)
    print("完整效能測試 (pyscrcpy)")
    print("=" * 60)

    # 檢查檔案
    print(f"\nADB: {ADB_EXE} {'✓' if ADB_EXE.exists() else '✗'}")
    print(f"pyscrcpy: {'✓' if PYSCRCPY_AVAILABLE else '✗ (pip install pyscrcpy)'}")

    if not ADB_EXE.exists():
        input("錯誤: 找不到 ADB！按 Enter 退出...")
        return

    # 檢查模板
    for name, path in TEMPLATES.items():
        print(f"{name}: {'✓' if path.exists() else '✗'}")
        if not path.exists():
            input("找不到模板！按 Enter 退出...")
            return

    # 檢查 ADB 連接
    print("\n檢查設備...")
    result = subprocess.run([str(ADB_EXE), "devices"], capture_output=True, text=True)
    lines = result.stdout.strip().split('\n')
    devices = [l for l in lines[1:] if 'device' in l and 'offline' not in l]
    if not devices:
        input("沒有設備連接！按 Enter 退出...")
        return
    print(f"設備: {devices[0].split()[0]}")

    # 獲取螢幕尺寸
    result = subprocess.run([str(ADB_EXE), "shell", "wm", "size"], capture_output=True, text=True)
    size_info = result.stdout.strip()
    print(f"螢幕: {size_info}")

    results = {}

    # 測試 1: ADB PNG
    results["ADB PNG"] = benchmark_method("ADB screencap -p (PNG)", adb_screenshot_png, 10)

    # 測試 2: ADB 原始
    results["ADB RAW"] = benchmark_method("ADB screencap 原始格式", adb_screenshot_raw, 20)

    # 測試 3: pyscrcpy 串流
    if PYSCRCPY_AVAILABLE:
        print("\n" + "=" * 60)
        print("啟動 pyscrcpy 串流...")
        print("=" * 60)

        stream = PyscrcpyStream(max_fps=60, bitrate=8000000, max_size=1600)

        if stream.start():
            time.sleep(0.5)
            results["PYSCRCPY"] = benchmark_method("pyscrcpy 視頻串流", stream.get_frame, 50)
            stream.stop()
        else:
            print("pyscrcpy 串流啟動失敗")
            results["PYSCRCPY"] = None
    else:
        print("\n跳過 pyscrcpy 測試 (需要 pip install pyscrcpy)")
        results["PYSCRCPY"] = None
    
    # 結果摘要
    print("\n" + "=" * 60)
    print("效能比較")
    print("=" * 60)
    print(f"{'方法':<20} {'平均':<12} {'FPS':<10} {'加速':<10}")
    print("-" * 60)
    
    baseline = results.get("ADB PNG", {})
    baseline_avg = baseline.get("avg", 1) if baseline else 1
    
    for name, data in results.items():
        if data and data.get("avg"):
            speedup = baseline_avg / data["avg"]
            print(f"{name:<20} {data['avg']*1000:>8.1f}ms  {data['fps']:>7.1f}  {speedup:>7.1f}x")
        else:
            print(f"{name:<20} {'N/A':<12}")
    
    print("=" * 60)
    
    # 推薦
    print("\n推薦:")
    best = None
    best_fps = 0
    for name, data in results.items():
        if data and data["fps"] > best_fps and data["success"] >= 0.9:
            best = name
            best_fps = data["fps"]
    
    if best:
        print(f"  使用 {best} 模式 ({best_fps:.1f} FPS)")
    
    input("\n按 Enter 退出...")


if __name__ == "__main__":
    main()
