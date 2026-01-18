import cv2
import numpy as np
import os

def find_and_draw(template_path, screenshot_path, output_name):
    print(f"\nProcessing {os.path.basename(screenshot_path)}...")
    template = cv2.imread(template_path)
    screenshot = cv2.imread(screenshot_path)
    if template is None or screenshot is None:
        print("Error loading images")
        return

    # Method 1: BGR
    res_bgr = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
    _, val_bgr, _, loc_bgr = cv2.minMaxLoc(res_bgr)
    center_bgr = (loc_bgr[0] + template.shape[1]//2, loc_bgr[1] + template.shape[0]//2)
    
    # Method 2: Masked (from script.py logic)
    gray_tpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray_tpl, 160, 255, cv2.THRESH_BINARY)
    res_mask = cv2.matchTemplate(screenshot, template, cv2.TM_CCORR_NORMED, mask=mask)
    _, val_mask, _, loc_mask = cv2.minMaxLoc(res_mask)
    center_mask = (loc_mask[0] + template.shape[1]//2, loc_mask[1] + template.shape[0]//2)

    # Output details
    print(f"  BGR: {val_bgr:.2%}, Center: {center_bgr}")
    print(f"  Masked: {val_mask:.2%}, Center: {center_mask}")

    # Draw and save
    out = screenshot.copy()
    # BGR - Red circle
    cv2.circle(out, center_bgr, 20, (0, 0, 255), 3)
    cv2.putText(out, f"BGR: {val_bgr:.2%}", (center_bgr[0]+25, center_bgr[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    
    # Masked - Green square
    cv2.rectangle(out, (loc_mask[0], loc_mask[1]), (loc_mask[0]+template.shape[1], loc_mask[1]+template.shape[0]), (0, 255, 0), 2)
    cv2.putText(out, f"Masked: {val_mask:.2%}", (loc_mask[0], loc_mask[1]-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

    cv2.imwrite(f"D:/Project/wvd/test/{output_name}.png", out)
    print(f"  Saved to {output_name}.png")

if __name__ == "__main__":
    t = "D:/Project/wvd/test/template.png"
    find_and_draw(t, "D:/Project/wvd/test/screenshot_original.png", "match_original")
    find_and_draw(t, "D:/Project/wvd/test/1.png", "match_1")
