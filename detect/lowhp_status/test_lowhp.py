import cv2
import os
import numpy as np

def analyze_roi_colors():
    """分析指定 ROI 區域的顏色百分比（紅色/綠色/其他）"""
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 定義 ROI 區域 [(x1,y1), (x2,y2)]
    rois = [
        # 第一排 (角色 0, 1, 2)
        {"name": "角色0", "coords": [(130, 1300), (190, 1330)]},
        {"name": "角色1", "coords": [(420, 1300), (480, 1330)]},
        {"name": "角色2", "coords": [(700, 1300), (760, 1330)]},
        # 第二排 (角色 3, 4, 5)
        {"name": "角色3", "coords": [(130, 1485), (190, 1505)]},
        {"name": "角色4", "coords": [(420, 1485), (480, 1505)]},
        {"name": "角色5", "coords": [(700, 1485), (760, 1505)]},
    ]
    
    # 遍歷資料夾中的圖片
    for filename in os.listdir(script_dir):
        if not filename.endswith('.png'):
            continue
            
        img_path = os.path.join(script_dir, filename)
        img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        
        if img is None:
            print(f"[{filename}] ❌ 無法載入")
            continue
        
        print(f"\n{'='*60}")
        print(f"圖片: {filename} (尺寸: {img.shape[1]}x{img.shape[0]})")
        print(f"{'='*60}")
        
        for roi_info in rois:
            name = roi_info["name"]
            (x1, y1), (x2, y2) = roi_info["coords"]
            
            # 確保座標在圖片範圍內
            if y2 > img.shape[0] or x2 > img.shape[1]:
                print(f"  [{name}] ⚠️ ROI 超出圖片範圍")
                continue
            
            # 擷取 ROI
            roi = img[y1:y2, x1:x2]
            
            # 轉換為 HSV 色彩空間
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            
            # 定義顏色範圍
            # 紅色 (兩個範圍，因為紅色在 HSV 中跨越 0 度)
            red_lower1 = np.array([0, 100, 100])
            red_upper1 = np.array([10, 255, 255])
            red_lower2 = np.array([160, 100, 100])
            red_upper2 = np.array([180, 255, 255])
            
            # 綠色
            green_lower = np.array([35, 100, 100])
            green_upper = np.array([85, 255, 255])
            
            # 黃色/橙色 (中等血量)
            yellow_lower = np.array([15, 100, 100])
            yellow_upper = np.array([35, 255, 255])
            
            # 計算各顏色遮罩
            red_mask1 = cv2.inRange(hsv, red_lower1, red_upper1)
            red_mask2 = cv2.inRange(hsv, red_lower2, red_upper2)
            red_mask = cv2.bitwise_or(red_mask1, red_mask2)
            green_mask = cv2.inRange(hsv, green_lower, green_upper)
            yellow_mask = cv2.inRange(hsv, yellow_lower, yellow_upper)
            
            # 計算像素總數
            total_pixels = roi.shape[0] * roi.shape[1]
            
            # 計算各顏色像素數
            red_pixels = cv2.countNonZero(red_mask)
            green_pixels = cv2.countNonZero(green_mask)
            yellow_pixels = cv2.countNonZero(yellow_mask)
            
            # 計算百分比
            red_pct = (red_pixels / total_pixels) * 100
            green_pct = (green_pixels / total_pixels) * 100
            yellow_pct = (yellow_pixels / total_pixels) * 100
            
            # 判斷狀態
            if red_pct > 10:
                status = "🔴 低血量"
            elif yellow_pct > 10:
                status = "🟡 中血量"
            elif green_pct > 10:
                status = "🟢 健康"
            else:
                status = "⚪ 未知/空"
            
            print(f"  [{name}] 紅:{red_pct:5.1f}% | 黃:{yellow_pct:5.1f}% | 綠:{green_pct:5.1f}% | {status}")

if __name__ == "__main__":
    analyze_roi_colors()
