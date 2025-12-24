#!/usr/bin/env python3
"""
測試 scrcpy 串流抓取幀並辨識小地圖樓層圖片
DH-R5-minimap.png 和 DH-R6-minimap.png

使用方式：
1. 確保模擬器已連接 (adb devices 可以看到設備)
2. 在遊戲中移動到有樓層標識的位置
3. 執行此腳本: python test_scrcpy_stream.py
4. 按 Ctrl+C 停止
"""

import subprocess
import time
import cv2
import numpy as np
import sys
from pathlib import Path

# 路徑設定 (相對於腳本位置)
SCRIPT_DIR = Path(__file__).parent
SCRCPY_PATH = SCRIPT_DIR / "scrcpy"
ADB_EXE = SCRCPY_PATH / "adb.exe"

# 模板圖片
TEMPLATES = {
    "DH-R5-minimap": SCRIPT_DIR / "resources" / "images" / "DH-R5-minimap.png",
    "DH-R6-minimap": SCRIPT_DIR / "resources" / "images" / "DH-R6-minimap.png",
}

# 偵測區域 (小地圖位置) - 右上角
# 格式: [x, y, width, height]
# 900x1600 螢幕，小地圖在右上角，約 x=700 開始
# 如果設為 None 則搜索整張圖
MINIMAP_ROI = [650, 0, 250, 250]


def adb_screenshot():
    """使用 ADB 截圖 (直式，不旋轉)"""
    try:
        result = subprocess.run(
            [str(ADB_EXE), "exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=10
        )
        
        if result.returncode == 0 and len(result.stdout) > 0:
            nparr = np.frombuffer(result.stdout, np.uint8)
            # 用 IMREAD_UNCHANGED 保留完整通道
            frame = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
            
            if frame is not None:
                # 如果是 RGBA (4通道)，轉換為 BGR (3通道)
                if len(frame.shape) == 3 and frame.shape[2] == 4:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            
            return frame
    except subprocess.TimeoutExpired:
        print("截圖超時！")
    except Exception as e:
        print(f"截圖錯誤: {e}")
    return None


def check_template(frame, template_path, roi=None, threshold=0.8):
    """
    模板匹配
    
    Args:
        frame: 截圖 (BGR numpy array)
        template_path: 模板圖片路徑
        roi: 搜索區域 [x, y, w, h]，None 則搜索整張圖
        threshold: 匹配閾值
        
    Returns:
        dict: {"found": bool, "match_val": float, "position": (x, y)}
    """
    if frame is None:
        return {"found": False, "match_val": 0, "position": None}
        
    template = cv2.imread(str(template_path))
    if template is None:
        print(f"無法載入模板: {template_path}")
        return {"found": False, "match_val": 0, "position": None}
    
    # 如果有 ROI，裁剪搜索區域
    search_area = frame
    offset_x, offset_y = 0, 0
    if roi:
        x, y, w, h = roi
        # 確保 ROI 在圖片範圍內
        h_max, w_max = frame.shape[:2]
        x = min(x, w_max - 1)
        y = min(y, h_max - 1)
        w = min(w, w_max - x)
        h = min(h, h_max - y)
        search_area = frame[y:y+h, x:x+w]
        offset_x, offset_y = x, y
    
    # 確保搜索區域比模板大
    if search_area.shape[0] < template.shape[0] or search_area.shape[1] < template.shape[1]:
        # ROI 太小，嘗試搜索整張圖
        search_area = frame
        offset_x, offset_y = 0, 0
    
    # 模板匹配
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
    """主測試程式"""
    print("=" * 60)
    print("小地圖樓層偵測測試 (DH-R5-minimap / DH-R6-minimap)")
    print("=" * 60)
    
    # 檢查 ADB
    if not ADB_EXE.exists():
        print(f"錯誤: 找不到 adb.exe: {ADB_EXE}")
        print("請確保 scrcpy 資料夾存在且包含 adb.exe")
        input("按 Enter 退出...")
        return
    
    print(f"✓ ADB 路徑: {ADB_EXE}")
        
    # 檢查模板圖片
    for name, path in TEMPLATES.items():
        if not path.exists():
            print(f"錯誤: 找不到模板圖片: {path}")
            input("按 Enter 退出...")
            return
        else:
            template = cv2.imread(str(path))
            print(f"✓ {name}: {template.shape[1]}x{template.shape[0]} 像素")
    
    # 檢查 ADB 連接
    print("\n檢查 ADB 設備...")
    try:
        result = subprocess.run([str(ADB_EXE), "devices"], capture_output=True, text=True, timeout=10)
        print(result.stdout.strip())
        
        # 檢查是否有設備連接
        lines = result.stdout.strip().split('\n')
        devices = [l for l in lines[1:] if l.strip() and 'device' in l]
        if not devices:
            print("\n錯誤: 沒有連接的設備！")
            print("請確保模擬器已啟動且 USB 調試已開啟")
            input("按 Enter 退出...")
            return
    except Exception as e:
        print(f"ADB 連接錯誤: {e}")
        input("按 Enter 退出...")
        return
    
    # 測試單次截圖
    print("\n測試截圖...")
    test_frame = adb_screenshot()
    if test_frame is None:
        print("錯誤: 無法截圖！")
        input("按 Enter 退出...")
        return
    print(f"✓ 截圖成功: {test_frame.shape[1]}x{test_frame.shape[0]}")
    
    # 儲存測試截圖
    cv2.imwrite("test_screenshot.png", test_frame)
    print("✓ 已儲存測試截圖: test_screenshot.png")
    
    print("\n" + "=" * 60)
    print("開始持續偵測... (按 Ctrl+C 停止)")
    print("=" * 60)
    print("格式: [耗時] R5匹配度% | R6匹配度%")
    print("-" * 60)
    
    frame_count = 0
    start_time = time.time()
    found_r5_count = 0
    found_r6_count = 0
    
    try:
        while True:
            loop_start = time.time()
            
            # 截圖
            frame = adb_screenshot()
            screenshot_time = time.time() - loop_start
            
            if frame is None:
                print("截圖失敗，等待重試...")
                time.sleep(1)
                continue
            
            frame_count += 1
            
            # 檢測兩個模板
            results = {}
            for name, path in TEMPLATES.items():
                result = check_template(frame, path, roi=MINIMAP_ROI, threshold=0.7)
                results[name] = result
            
            detection_time = time.time() - loop_start - screenshot_time
            total_time = time.time() - loop_start
            
            # 顯示結果
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
            
            # 如果找到任何一個，儲存截圖
            if r5_found or r6_found:
                timestamp = time.strftime("%H%M%S")
                found_name = "R5" if r5_found else "R6"
                filename = f"detected_{found_name}_{timestamp}.png"
                cv2.imwrite(filename, frame)
                print(f"    >>> 已儲存截圖: {filename}")
            
            # 等待一小段時間
            time.sleep(0.1)
                
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
