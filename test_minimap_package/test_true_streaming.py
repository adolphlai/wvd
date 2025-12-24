#!/usr/bin/env python3
"""
測試 scrcpy 真正的視頻串流模式
使用 FFmpeg 解碼 scrcpy 輸出的視頻流

理論速度: ~30ms/幀 (比 ADB 快 20 倍)

使用方式：
1. 確保模擬器已連接
2. 執行: python test_true_streaming.py
3. 按 Ctrl+C 停止
"""

import subprocess
import time
import cv2
import numpy as np
import threading
import queue
from pathlib import Path

# 路徑設定
SCRIPT_DIR = Path(__file__).parent
SCRCPY_PATH = SCRIPT_DIR / "scrcpy"
SCRCPY_EXE = SCRCPY_PATH / "scrcpy.exe"
ADB_EXE = SCRCPY_PATH / "adb.exe"

# 模板圖片
TEMPLATES = {
    "DH-R5-minimap": SCRIPT_DIR / "resources" / "images" / "DH-R5-minimap.png",
    "DH-R6-minimap": SCRIPT_DIR / "resources" / "images" / "DH-R6-minimap.png",
}

# 偵測區域 (右上角小地圖)
MINIMAP_ROI = [650, 0, 250, 250]


class ScrcpyVideoStream:
    """
    scrcpy 視頻串流捕獲器
    使用 scrcpy 輸出視頻流到管道，用 FFmpeg/OpenCV 解碼
    """
    
    def __init__(self, scrcpy_exe, max_size=1600, max_fps=30):
        self.scrcpy_exe = Path(scrcpy_exe)
        self.max_size = max_size
        self.max_fps = max_fps
        
        self.process = None
        self.capture = None
        self.frame_queue = queue.Queue(maxsize=2)
        self.running = False
        self.reader_thread = None
        
        self.frame_count = 0
        self.start_time = None
        
    def start(self):
        """啟動 scrcpy 視頻串流"""
        print("啟動 scrcpy 視頻串流...")
        
        # scrcpy 參數
        cmd = [
            str(self.scrcpy_exe),
            "--no-window",           # 不顯示視窗
            "--no-audio",            # 不傳音頻
            "--video-codec=h264",    # H.264 編碼
            f"--max-size={self.max_size}",
            f"--max-fps={self.max_fps}",
            "--video-bit-rate=4M",
            "--record=-",            # 輸出到 stdout
            "--record-format=mp4",   # MP4 格式
        ]
        
        print(f"命令: {' '.join(cmd)}")
        
        try:
            # 啟動 scrcpy，輸出到管道
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=10**8
            )
            
            # 等待 scrcpy 初始化
            time.sleep(2)
            
            # 檢查是否正常啟動
            if self.process.poll() is not None:
                stderr = self.process.stderr.read().decode('utf-8', errors='ignore')
                print(f"scrcpy 啟動失敗: {stderr}")
                return False
            
            # 使用 OpenCV VideoCapture 從管道讀取
            # 注意：這在 Windows 上可能有問題，需要用 FFmpeg
            
            self.running = True
            self.start_time = time.time()
            
            # 啟動讀取線程
            self.reader_thread = threading.Thread(target=self._read_frames, daemon=True)
            self.reader_thread.start()
            
            print("串流已啟動！")
            return True
            
        except Exception as e:
            print(f"啟動失敗: {e}")
            return False
    
    def _read_frames(self):
        """從管道讀取視頻幀"""
        # 嘗試用 OpenCV 直接讀取管道
        # 這在 Windows 上可能不工作，需要改用其他方法
        
        try:
            # 方法1: 使用 OpenCV VideoCapture 讀取管道
            # cap = cv2.VideoCapture(f"pipe:{self.process.stdout.fileno()}")
            
            # 方法2: 直接讀取 H.264 流並解碼
            # 這需要更複雜的實現
            
            # 先試試讀取原始數據
            buffer = b""
            while self.running:
                chunk = self.process.stdout.read(4096)
                if not chunk:
                    break
                buffer += chunk
                
                # 這裡需要解析 MP4/H.264 流
                # 實際上這很複雜，需要專門的解碼器
                
        except Exception as e:
            print(f"讀取錯誤: {e}")
    
    def get_frame(self):
        """獲取最新幀"""
        try:
            return self.frame_queue.get_nowait()
        except queue.Empty:
            return None
    
    def stop(self):
        """停止串流"""
        self.running = False
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except:
                self.process.kill()
        print("串流已停止")


class ScrcpyTcpStream:
    """
    使用 TCP 方式獲取 scrcpy 視頻流
    通過 adb forward 將視頻流轉發到本地端口
    """
    
    def __init__(self, adb_exe, port=27183, max_size=1600):
        self.adb_exe = Path(adb_exe)
        self.port = port
        self.max_size = max_size
        self.running = False
        self.frame = None
        self.frame_lock = threading.Lock()
        
    def start(self):
        """設置 ADB 端口轉發"""
        # 這個方法需要在設備上運行 scrcpy-server
        # 然後通過 socket 接收視頻流
        # 實現相當複雜
        pass


def scrcpy_screenshot_raw():
    """
    原始模式截圖 (作為對照)
    """
    try:
        result = subprocess.run(
            [str(ADB_EXE), "exec-out", "screencap"],
            capture_output=True,
            timeout=5
        )
        
        if result.returncode == 0 and len(result.stdout) > 0:
            data = result.stdout
            if len(data) < 12:
                return None
                
            w = int.from_bytes(data[0:4], 'little')
            h = int.from_bytes(data[4:8], 'little')
            
            pixels = data[12:]
            expected_size = w * h * 4
            
            if len(pixels) >= expected_size:
                frame = np.frombuffer(pixels[:expected_size], dtype=np.uint8)
                frame = frame.reshape((h, w, 4))
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
                return frame
                
    except Exception as e:
        print(f"截圖錯誤: {e}")
    return None


def check_template(frame, template_path, roi=None, threshold=0.8):
    """模板匹配"""
    if frame is None:
        return {"found": False, "match_val": 0, "position": None}
        
    template = cv2.imread(str(template_path))
    if template is None:
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
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        
        found = max_val >= threshold
        position = (max_loc[0] + offset_x, max_loc[1] + offset_y) if found else None
        
        return {"found": found, "match_val": max_val, "position": position}
    except:
        return {"found": False, "match_val": 0, "position": None}


def test_method_comparison():
    """測試不同方法的速度比較"""
    print("=" * 60)
    print("截圖方法速度比較")
    print("=" * 60)
    
    methods = [
        ("ADB screencap 原始模式", scrcpy_screenshot_raw),
    ]
    
    results = {}
    
    for name, func in methods:
        print(f"\n測試: {name}")
        times = []
        
        for i in range(10):
            start = time.time()
            frame = func()
            elapsed = time.time() - start
            
            if frame is not None:
                times.append(elapsed)
                print(f"  #{i+1}: {elapsed*1000:.1f}ms")
            else:
                print(f"  #{i+1}: 失敗")
        
        if times:
            avg = sum(times) / len(times)
            results[name] = avg
            print(f"  平均: {avg*1000:.1f}ms ({1/avg:.1f} FPS)")
    
    return results


def main():
    """主程式"""
    print("=" * 60)
    print("scrcpy 真實串流模式測試")
    print("=" * 60)
    
    # 檢查檔案
    if not SCRCPY_EXE.exists():
        print(f"錯誤: 找不到 scrcpy.exe: {SCRCPY_EXE}")
        input("按 Enter 退出...")
        return
    
    if not ADB_EXE.exists():
        print(f"錯誤: 找不到 adb.exe: {ADB_EXE}")
        input("按 Enter 退出...")
        return
    
    print(f"✓ scrcpy: {SCRCPY_EXE}")
    print(f"✓ ADB: {ADB_EXE}")
    
    # 檢查模板
    for name, path in TEMPLATES.items():
        if not path.exists():
            print(f"錯誤: 找不到模板: {path}")
            input("按 Enter 退出...")
            return
        template = cv2.imread(str(path))
        print(f"✓ {name}: {template.shape[1]}x{template.shape[0]}")
    
    # 檢查 ADB
    print("\n檢查 ADB...")
    result = subprocess.run([str(ADB_EXE), "devices"], capture_output=True, text=True)
    print(result.stdout.strip())
    
    if "device" not in result.stdout:
        print("錯誤: 沒有設備連接！")
        input("按 Enter 退出...")
        return
    
    # 測試速度比較
    print("\n")
    test_method_comparison()
    
    # 嘗試啟動真正的串流
    print("\n" + "=" * 60)
    print("嘗試啟動 scrcpy 視頻串流...")
    print("=" * 60)
    
    stream = ScrcpyVideoStream(SCRCPY_EXE)
    
    if stream.start():
        print("串流啟動成功！")
        print("但是，解碼 H.264 流需要額外的 FFmpeg 綁定")
        print("目前這個功能還在開發中...")
        time.sleep(3)
        stream.stop()
    else:
        print("串流啟動失敗")
        print("\n注意: 真正的視頻串流需要：")
        print("  1. FFmpeg Python 綁定 (如 ffmpeg-python)")
        print("  2. 或者使用 scrcpy 的 --v4l2-sink (僅限 Linux)")
        print("  3. 或者使用 ADB shell 的 screenrecord 管道")
    
    # 退回到原始模式進行持續偵測
    print("\n" + "=" * 60)
    print("使用原始模式持續偵測 (目前最快的可用方法)")
    print("按 Ctrl+C 停止")
    print("=" * 60)
    
    frame_count = 0
    start_time = time.time()
    found_r5 = 0
    found_r6 = 0
    
    try:
        while True:
            loop_start = time.time()
            
            frame = scrcpy_screenshot_raw()
            shot_time = time.time() - loop_start
            
            if frame is None:
                print("截圖失敗")
                time.sleep(0.5)
                continue
            
            frame_count += 1
            
            # 偵測
            results = {}
            for name, path in TEMPLATES.items():
                results[name] = check_template(frame, path, roi=MINIMAP_ROI, threshold=0.7)
            
            total = time.time() - loop_start
            
            r5 = results["DH-R5-minimap"]
            r6 = results["DH-R6-minimap"]
            
            if r5["found"]:
                found_r5 += 1
            if r6["found"]:
                found_r6 += 1
            
            status_r5 = "<<找到!>>" if r5["found"] else ""
            status_r6 = "<<找到!>>" if r6["found"] else ""
            
            print(f"[{total*1000:.0f}ms] "
                  f"R5: {r5['match_val']*100:5.1f}% {status_r5:10} | "
                  f"R6: {r6['match_val']*100:5.1f}% {status_r6:10}")
            
            time.sleep(0.02)
            
    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        fps = frame_count / elapsed if elapsed > 0 else 0
        
        print("\n" + "=" * 60)
        print(f"測試結束！")
        print(f"  幀數: {frame_count}")
        print(f"  時間: {elapsed:.1f}s")
        print(f"  FPS: {fps:.1f}")
        print(f"  R5 找到: {found_r5}")
        print(f"  R6 找到: {found_r6}")
        print("=" * 60)
        input("按 Enter 退出...")


if __name__ == "__main__":
    main()
