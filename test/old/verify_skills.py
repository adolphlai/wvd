import cv2
import numpy as np
import os

def test_skill_matching(template_path, screenshot_path):
    print(f"\n--- Testing: {os.path.basename(screenshot_path)} ---")
    
    # Load images
    template = cv2.imread(template_path)
    screenshot = cv2.imread(screenshot_path)
    
    if template is None or screenshot is None:
        print(f"Error: Could not load {template_path} or {screenshot_path}")
        return

    # Method 1: Standard BGR Matching (TM_CCOEFF_NORMED)
    res_bgr = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
    _, max_val_bgr, _, max_loc_bgr = cv2.minMaxLoc(res_bgr)
    center_bgr = (max_loc_bgr[0] + template.shape[1]//2, max_loc_bgr[1] + template.shape[0]//2)
    print(f"Standard BGR Match: {max_val_bgr:.2%}, Center: {center_bgr}")

    # Method 2: Masked Matching (TM_CCORR_NORMED with mask) - As used in script.py for skills
    gray_tpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray_tpl, 160, 255, cv2.THRESH_BINARY)
    
    res_mask = cv2.matchTemplate(screenshot, template, cv2.TM_CCORR_NORMED, mask=mask)
    _, max_val_mask, _, max_loc_mask = cv2.minMaxLoc(res_mask)
    center_mask = (max_loc_mask[0] + template.shape[1]//2, max_loc_mask[1] + template.shape[0]//2)
    print(f"Masked Match (CCORR_NORMED): {max_val_mask:.2%}, Center: {center_mask}")

if __name__ == "__main__":
    template = "D:/Project/wvd/test/template.png"
    screens = ["D:/Project/wvd/test/screenshot_original.png", "D:/Project/wvd/test/1.png"]
    
    for s in screens:
        test_skill_matching(template, s)
