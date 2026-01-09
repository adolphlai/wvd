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

def get_hsv_stats(img):
    if img is None: return np.array([0,0,0])
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return np.mean(hsv, axis=(0,1))

def main():
    base_dir = r"D:\Project\wvd\detect"
    poison_icon_path = os.path.join(base_dir, "中毒", "Poison_icon.png")
    icon = load_image(poison_icon_path)
    if icon is None:
        print("Poison icon not found!")
        return
    
    mh, mw = icon.shape[:2]
    icon_hsv = get_hsv_stats(icon)

    all_pngs = []
    for root, dirs, files in os.walk(base_dir):
        for f in files:
            name_lower = f.lower()
            if f.lower().endswith(".png") and "icon" not in name_lower and "result" not in name_lower and "mask" not in name_lower and "cropped" not in name_lower:
                all_pngs.append(os.path.join(root, f))

    print(f"Total images to audit: {len(all_pngs)}")
    print(f"{'Folder':<15} | {'Image':<15} | {'Char':<4} | {'Match %':<8} | {'Hue':<6} | {'Sat':<6} | {'Status'}")
    print("-" * 90)

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
            mx, my = max_loc
            best_match_area = roi[my:my+mh, mx:mx+mw]
            area_hsv = get_hsv_stats(best_match_area)
            
            # 中毒判定規則 (Hue ~127, Sat ~85)
            hue_dist = abs(area_hsv[0] - icon_hsv[0])
            sat_dist = abs(area_hsv[1] - icon_hsv[1])
            color_match = hue_dist < 15 and sat_dist < 40 and area_hsv[1] > 30
            
            is_poison = (match_pct >= 75) and color_match
            
            if is_poison:
                positive_count += 1
                print(f"{folder:<15} | {name:<15} | {i:<4} | {match_pct:>6.2f}% | {area_hsv[0]:>6.1f} | {area_hsv[1]:>6.1f} | DETECTED")
            elif match_pct > 75:
                # 記錄潛在誤判 (形狀像但顏色不對)
                print(f"{folder:<15} | {name:<15} | {i:<4} | {match_pct:>6.2f}% | {area_hsv[0]:>6.1f} | {area_hsv[1]:>6.1f} | (Filter Out)")

    print("-" * 90)
    print(f"Audit Complete. Total DETECTED: {positive_count}")

if __name__ == "__main__":
    main()
