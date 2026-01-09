import cv2
import numpy as np
import os

ROIS = [
    (137, 1230, 162, 60),  # C0
    (420, 1230, 165, 60),  # C1
    (704, 1230, 167, 60),  # C2
    (137, 1405, 162, 60),  # C3
    (420, 1405, 165, 60),  # C4
    (704, 1405, 167, 60),  # C5
]

def load_image(path):
    try:
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except: return None

def main():
    path = r"D:\Project\wvd\detect\劇毒"
    icon = load_image(os.path.join(path, "poisonous_icon.png"))
    screen = load_image(os.path.join(path, "poisonous1.png"))
    
    print(f"Template Size: {icon.shape}")
    print(f"{'Char':<5} | {'Match %':<8} | {'Avg HSV in Match Area'}")
    print("-" * 40)
    
    for i, (x, y, w, h) in enumerate(ROIS):
        roi = screen[y:y+h, x:x+w]
        res = cv2.matchTemplate(roi, icon, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        
        # Get the actual matched area in the ROI
        mh, mw = icon.shape[:2]
        mx, my = max_loc
        match_area = roi[my:my+mh, mx:mx+mw]
        
        hsv = cv2.cvtColor(match_area, cv2.COLOR_BGR2HSV)
        avg_hsv = np.mean(hsv, axis=(0,1))
        
        print(f"C{i:<4} | {max_val*100:>6.2f}% | {avg_hsv}")

if __name__ == "__main__":
    main()
