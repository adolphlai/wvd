import cv2
import numpy as np
import os

ROIS = [
    (137, 1230, 162, 60), (420, 1230, 165, 60), (704, 1230, 167, 60),
    (137, 1405, 162, 60), (420, 1405, 165, 60), (704, 1405, 167, 60),
]

def load_image(path):
    try:
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except: return None

def main():
    path = r"D:\Project\wvd\detect\stone"
    icon = load_image(os.path.join(path, "stone_icon.png"))
    if icon is None: return
    
    test_files = [f for f in os.listdir(path) if f.startswith("stone") and not f.endswith("_icon.png") and f.endswith(".png")]

    print(f"{'Image':<12} | {'Char':<4} | {'Match %':<8} | {'Top White':<9} | {'Status'}")
    print("-" * 60)

    for img_name in sorted(test_files):
        screen = load_image(os.path.join(path, img_name))
        if screen is None: continue
        
        for i, (x, y, w, h) in enumerate(ROIS):
            roi = screen[y:y+h, x:x+w]
            res = cv2.matchTemplate(roi, icon, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            
            match_pct = max_val * 100
            
            # 針對匹配到的區域進行顏色分析
            ih, iw = icon.shape[:2]
            mx, my = max_loc
            best_match_area = roi[my:my+ih, mx:mx+iw]
            
            # 取上半部 (上半 20 像素)
            top_half = best_match_area[:ih//2, :]
            top_hsv = cv2.cvtColor(top_half, cv2.COLOR_BGR2HSV)
            # 白色判定: 飽和度低 (< 40), 亮度高 (> 180)
            white_mask = cv2.inRange(top_hsv, np.array([0, 0, 180]), np.array([180, 40, 255]))
            white_count = cv2.countNonZero(white_mask)
            
            # 新規則: 匹配度 > 75% 且 上半部白色像素在合理範圍內 (50 到 130)
            # 避免抓到太白 (像素 > 200) 的其他 UI 或 背景
            is_stone = (match_pct >= 75) and (50 < white_count < 130)
            
            status = "DETECTED" if is_stone else "-"
            
            # 只顯示有潛力或已偵測的結果
            if match_pct > 60:
                print(f"{img_name:<12} | {i:<4} | {match_pct:>6.2f}% | {white_count:>9} | {status}")

if __name__ == "__main__":
    main()
