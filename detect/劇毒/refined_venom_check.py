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

def get_hsv_stats(img):
    if img is None: return np.array([0,0,0])
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return np.mean(hsv, axis=(0,1))

def main():
    path = r"D:\Project\wvd\detect\劇毒"
    icon = load_image(os.path.join(path, "poisonous_icon.png"))
    if icon is None: return
    
    icon_hsv = get_hsv_stats(icon)
    test_files = [f for f in os.listdir(path) if f.startswith("poisonous") and not f.endswith("_icon.png") and f.endswith(".png")]

    for img_name in test_files:
        screen = load_image(os.path.join(path, img_name))
        if screen is None: continue
        
        print(f"\n[Testing Image: {img_name}]")
        print(f"{'Char':<5} | {'Match %':<8} | {'Match Area Avg HSV':<21} | {'Status'}")
        print("-" * 65)

        for i, (x, y, w, h) in enumerate(ROIS):
            roi = screen[y:y+h, x:x+w]
            res = cv2.matchTemplate(roi, icon, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            
            mh, mw = icon.shape[:2]
            mx, my = max_loc
            match_area = roi[my:my+mh, mx:mx+mw]
            area_hsv = get_hsv_stats(match_area)
            
            match_pct = max_val * 100
            hue_dist = abs(area_hsv[0] - icon_hsv[0])
            # Color match: Purple hue (around 130), Saturation > 50
            color_match = hue_dist < 20 and area_hsv[1] > 50
            
            status = "DETECTED" if (match_pct >= 75 and color_match) else "-"
            print(f"C{i:<4} | {match_pct:>6.2f}% | {str(np.round(area_hsv, 1)):<21} | {status}")

if __name__ == "__main__":
    main()
