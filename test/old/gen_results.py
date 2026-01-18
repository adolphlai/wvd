import cv2
import numpy as np
import os

def find_with_roi(template_path, screenshot_path, roi, output_name):
    template = cv2.imread(template_path)
    screenshot = cv2.imread(screenshot_path)
    if template is None or screenshot is None:
        print(f"Error: {screenshot_path} not found")
        return

    x1, y1, x2, y2 = roi
    search_area = screenshot[y1:y2, x1:x2]
    
    # BGR
    res_bgr = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
    _, val_bgr, _, loc_bgr = cv2.minMaxLoc(res_bgr)
    center_bgr = (x1 + loc_bgr[0] + template.shape[1]//2, y1 + loc_bgr[1] + template.shape[0]//2)
    
    # Masked
    gray_tpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray_tpl, 160, 255, cv2.THRESH_BINARY)
    res_mask = cv2.matchTemplate(search_area, template, cv2.TM_CCORR_NORMED, mask=mask)
    _, val_mask, _, loc_mask = cv2.minMaxLoc(res_mask)
    center_mask = (x1 + loc_mask[0] + template.shape[1]//2, y1 + loc_mask[1] + template.shape[0]//2)

    # 畫圖
    out = screenshot.copy()
    # ROI 藍框
    cv2.rectangle(out, (x1, y1), (x2, y2), (255, 0, 0), 2)
    
    # BGR - 紅圈
    cv2.circle(out, center_bgr, 15, (0, 0, 255), 3)
    cv2.putText(out, f"BGR:{val_bgr:.0%}", (center_bgr[0]+20, center_bgr[1]-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    
    # Masked - 綠框
    tl_mask = (x1 + loc_mask[0], y1 + loc_mask[1])
    cv2.rectangle(out, tl_mask, (tl_mask[0]+template.shape[1], tl_mask[1]+template.shape[0]), (0, 255, 0), 2)
    cv2.putText(out, f"Masked:{val_mask:.0%}", (tl_mask[0], tl_mask[1]-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    cv2.imwrite(f"D:/Project/wvd/test/{output_name}", out)
    print(f"Saved {output_name}: BGR {val_bgr:.2%} {center_bgr}, Masked {val_mask:.2%} {center_mask}")

if __name__ == "__main__":
    t = "D:/Project/wvd/test/template.png"
    roi = [95, 971, 799, 1136]
    
    for i in range(1, 5):
        find_with_roi(t, f"D:/Project/wvd/test/{i}.png", roi, f"result_{i}.png")
