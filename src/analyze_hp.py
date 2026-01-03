import cv2
import numpy as np
import os

def analyze_hp_in_folder(folder_path, roi):
    if not os.path.exists(folder_path):
        print(f"Error: Folder not found at {folder_path}")
        return

    x1, y1 = roi[0]
    x2, y2 = roi[1]
    
    # Red range in HSV
    lower_red1 = np.array([0, 70, 50])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, 70, 50])
    upper_red2 = np.array([180, 255, 255])

    print(f"{'Filename':<30} | {'Red Ratio':<10} | {'Red Pixels':<10} | {'Status'}")
    print("-" * 70)

    for filename in os.listdir(folder_path):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
            file_path = os.path.join(folder_path, filename)
            img = cv2.imread(file_path)
            
            if img is None:
                print(f"{filename:<30} | {'Error':<10} | {'-':<10} | Could not load")
                continue

            # Check if image is large enough for ROI
            if img.shape[0] < y2 or img.shape[1] < x2:
                print(f"{filename:<30} | {'Error':<10} | {'-':<10} | Image too small")
                continue

            crop = img[y1:y2, x1:x2]
            
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            
            mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
            mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
            mask = mask1 + mask2
            
            red_pixels = cv2.countNonZero(mask)
            total_pixels = crop.shape[0] * crop.shape[1]
            red_ratio = red_pixels / total_pixels
            
            # Simple heuristic for "Is Red?" (e.g., > 50% red)
            is_red = "YES" if red_ratio > 0.5 else "NO"
            
            print(f"{filename:<30} | {red_ratio:.2%}    | {red_pixels:<10} | {is_red}")

if __name__ == "__main__":
    # directory containing the screenshots
    target_dir = r"D:\Project\wvd\src\debug_screenshots"
    # ROI: (400, 1307) -> (477, 1335)
    target_roi = ((400, 1307), (477, 1335))
    
    analyze_hp_in_folder(target_dir, target_roi)
