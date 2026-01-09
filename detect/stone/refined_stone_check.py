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
    path = r"D:\Project\wvd\detect\stone"
    icon = load_image(os.path.join(path, "stone_icon.png"))
    if icon is None: return
    
    icon_hsv = get_hsv_stats(icon)
    print(f"Stone Icon (Template) Avg HSV: {icon_hsv}")
    
    test_files = [f for f in os.listdir(path) if f.startswith("stone") and not f.endswith("_icon.png") and f.endswith(".png")]

    for img_name in sorted(test_files):
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
            
            # Saturation check for Stone: it is grayish, so Saturation should be very low
            # Icon has Sat ~12. We'll allow up to ~40 to handle UI highlights or subtle shades
            is_low_sat = area_hsv[1] < 45
            
            status = "DETECTED" if (match_pct >= 75 and is_low_sat) else "-"
            print(f"C{i:<4} | {match_pct:>6.2f}% | {str(np.round(area_hsv, 1)):<21} | {status}")

if __name__ == "__main__":
    main()
