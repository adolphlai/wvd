import cv2
import numpy as np
import os

def analyze_fear():
    script_dir = r"D:\Project\wvd\detect\fear_sample"
    screenshot_path = os.path.join(script_dir, "fear.png")
    icon_path = os.path.join(script_dir, "fear_icon.png")
    
    if not os.path.exists(screenshot_path) or not os.path.exists(icon_path):
        print("Files not found")
        return

    img = cv2.imdecode(np.fromfile(screenshot_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    template = cv2.imdecode(np.fromfile(icon_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    
    print(f"Analyzing Fear Icon Detection...")
    print(f"Screenshot size: {img.shape}")
    print(f"Template size: {template.shape}")

    # Standard Matching
    res = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    print(f"Max Match Value: {max_val*100:.2f}% at {max_loc}")
    
    if max_val > 0.70:
        top_left = max_loc
        h, w = template.shape[:2]
        matched_region = img[top_left[1]:top_left[1]+h, top_left[0]:top_left[0]+w]
        
        # Color Analysis (HSV)
        hsv = cv2.cvtColor(matched_region, cv2.COLOR_BGR2HSV)
        avg_hue = np.mean(hsv[:,:,0])
        avg_sat = np.mean(hsv[:,:,1])
        avg_val = np.mean(hsv[:,:,2])
        print(f"HSV Analysis: H={avg_hue:.1f}, S={avg_sat:.1f}, V={avg_val:.1f}")
        
        # Save matched region for verification (optional)
        # cv2.imwrite("matched_fear.png", matched_region)

if __name__ == "__main__":
    analyze_fear()
