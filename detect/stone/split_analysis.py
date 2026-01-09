import cv2
import numpy as np
import os

ROIS = [
    (137, 1230, 162, 60), # C0 (Top-left)
    (137, 1405, 162, 60), # C3 (Bottom-left, active stone)
]

def load_image(path):
    data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)

def main():
    path = r"D:\Project\wvd\detect\stone\stone1.png"
    img = load_image(path)
    if img is None: return

    for i, (x, y, w, h) in enumerate(ROIS):
        roi = img[y:y+h, x:x+w]
        
        # Split ROI into top and bottom halves
        mid = h // 2
        top_half = roi[:mid, :]
        bottom_half = roi[mid:, :]
        
        # Analyze top (White/Light)
        top_hsv = cv2.cvtColor(top_half, cv2.COLOR_BGR2HSV)
        # White-ish: Sat < 30, Val > 150
        white_mask = cv2.inRange(top_hsv, np.array([0, 0, 180]), np.array([180, 40, 255]))
        white_px = cv2.countNonZero(white_mask)
        
        # Analyze bottom (Gray)
        bot_hsv = cv2.cvtColor(bottom_half, cv2.COLOR_BGR2HSV)
        # Gray-ish: Sat < 30, Val 80-180
        gray_mask = cv2.inRange(bot_hsv, np.array([0, 0, 80]), np.array([180, 40, 180]))
        gray_px = cv2.countNonZero(gray_mask)
        
        print(f"ROI for Character {0 if i==0 else 3}:")
        print(f"  Top White Pixels (Sat<40, Val>180): {white_px}")
        print(f"  Bottom Gray Pixels (Sat<40, Val 80-180): {gray_px}")
        print("-" * 30)

if __name__ == "__main__":
    main()
