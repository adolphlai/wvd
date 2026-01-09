import cv2
import numpy as np
import os

BASE_DIR = r"D:\Project\wvd\detect"
FEAR_TEMPLATE = r"D:\Project\wvd\resources\images\detect\fear_icon.png"

def compare_images():
    # Load Template
    template = cv2.imdecode(np.fromfile(FEAR_TEMPLATE, dtype=np.uint8), cv2.IMREAD_COLOR)
    if template is None:
        print("Template not found")
        return

    h, w = template.shape[:2]
    
    # Define targets
    targets = [
        ("Fear", r"D:\Project\wvd\detect\fear_sample\fear.png"),
        ("Cursed", r"D:\Project\wvd\detect\demon_status\cursed.png"),
        ("Poison", r"D:\Project\wvd\detect\劇毒\poisonous1.png")
    ]
    
    print(f"Template Size: {w}x{h}")
    
    for label, path in targets:
        if not os.path.exists(path):
            print(f"Skipping {label}, file not found.")
            continue
            
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        
        # Match
        res = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        
        top_left = max_loc
        crop = img[top_left[1]:top_left[1]+h, top_left[0]:top_left[0]+w]
        
        # Compute Diff
        # Need to resize crop if slightly different? No, template match ensures size match.
        
        # Pixel-wise diff statistics
        diff = cv2.absdiff(template, crop)
        mean_diff = np.mean(diff, axis=(0,1))
        
        print(f"\n[{label}] Match: {max_val*100:.2f}%")
        print(f"Mean Diff (BGR): {mean_diff}")
        
        # HSV Analysis of the crop
        hsv_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        h_mean = np.mean(hsv_crop[:,:,0])
        s_mean = np.mean(hsv_crop[:,:,1])
        v_mean = np.mean(hsv_crop[:,:,2])
        print(f"HSV Mean: H={h_mean:.1f}, S={s_mean:.1f}, V={v_mean:.1f}")

        # Check Red Channel Difference specifically (since Cyan vs Red/Purple)
        # Fear (Cyan) has low Red. Cursed/Poison might have higher Red.
        r_mean = np.mean(crop[:,:,2])
        print(f"Red Channel Mean: {r_mean:.2f}")

        # Grid analysis: Split into 3x3 grid to find specific differing regions
        # Eyes are usually in the middle or top-middle.
        print("Grid Analysis (Red Channel Mean):")
        gh = h // 3
        gw = w // 3
        for r in range(3):
            row_str = ""
            for c in range(3):
                y1, y2 = r*gh, (r+1)*gh
                x1, x2 = c*gw, (c+1)*gw
                cell = crop[y1:y2, x1:x2]
                cell_r = np.mean(cell[:,:,2])
                row_str += f"{cell_r:6.1f} "
            print(f"  Row {r}: {row_str}")

if __name__ == "__main__":
    compare_images()
