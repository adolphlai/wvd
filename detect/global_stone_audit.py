import cv2
import numpy as np
import os

ROIS = [
    (120, 1210, 250, 80), (380, 1210, 250, 80), (640, 1210, 250, 80),
    (120, 1390, 250, 80), (380, 1390, 250, 80), (640, 1390, 250, 80),
]

def load_image(path):
    try:
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except: return None

def main():
    base_dir = r"D:\Project\wvd\detect"
    stone_icon_path = os.path.join(base_dir, "stone", "stone_icon.png")
    icon = load_image(stone_icon_path)
    if icon is None:
        print("Stone icon not found!")
        return
    
    mh, mw = icon.shape[:2]

    # 遞迴尋找所有 PNG 檔案
    all_pngs = []
    for root, dirs, files in os.walk(base_dir):
        for f in files:
            name_lower = f.lower()
            if f.lower().endswith(".png") and "icon" not in name_lower and "result" not in name_lower and "mask" not in name_lower and "cropped" not in name_lower:
                all_pngs.append(os.path.join(root, f))

    print(f"Total images to audit: {len(all_pngs)}")
    print(f"{'Folder':<15} | {'Image':<15} | {'Char':<4} | {'Match %':<8} | {'Top White':<9} | {'Status'}")
    print("-" * 85)

    positive_count = 0
    for img_path in sorted(all_pngs):
        screen = load_image(img_path)
        if screen is None or screen.shape[0] < 1600: continue
        
        folder = os.path.basename(os.path.dirname(img_path))
        name = os.path.basename(img_path)

        for i, (x, y, w, h) in enumerate(ROIS):
            if y + h > screen.shape[0] or x + w > screen.shape[1]: continue
            
            roi = screen[y:y+h, x:x+w]
            res = cv2.matchTemplate(roi, icon, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            
            match_pct = max_val * 100
            
            # 取得匹配區域
            mx, my = max_loc
            best_match_area = roi[my:my+mh, mx:mx+mw]
            
            # 顏色分析
            top_half = best_match_area[:mh//2, :]
            top_hsv = cv2.cvtColor(top_half, cv2.COLOR_BGR2HSV)
            white_mask = cv2.inRange(top_hsv, np.array([0, 0, 180]), np.array([180, 40, 255]))
            white_count = cv2.countNonZero(white_mask)
            
            is_stone = (match_pct >= 75) and (50 < white_count < 130)
            
            # 如果判定為石化，或者形狀高度相似但被顏色擋住，則輸出以便檢查誤判
            if is_stone:
                positive_count += 1
                print(f"{folder:<15} | {name:<15} | {i:<4} | {match_pct:>6.2f}% | {white_count:>9} | DETECTED")
            elif match_pct > 80:
                # 這裡就是潛在的「誤判風險」，我們看看為什麼它們被過濾掉了
                print(f"{folder:<15} | {name:<15} | {i:<4} | {match_pct:>6.2f}% | {white_count:>9} | (Blocked: {white_count})")

    print("-" * 85)
    print(f"Audit Complete. Total DETECTED: {positive_count}")

if __name__ == "__main__":
    main()
