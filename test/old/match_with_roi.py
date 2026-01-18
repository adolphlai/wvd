import cv2
import numpy as np
import os

def find_with_roi(template_path, screenshot_path, roi, output_name):
    """
    在指定 ROI 範圍內進行模板匹配
    Args:
        roi: [x1, y1, x2, y2] 格式
    """
    print(f"\nProcessing {os.path.basename(screenshot_path)} with ROI {roi}...")
    template = cv2.imread(template_path)
    screenshot = cv2.imread(screenshot_path)
    if template is None or screenshot is None:
        print("Error loading images")
        return

    x1, y1, x2, y2 = roi
    search_area = screenshot[y1:y2, x1:x2]
    
    # Method 1: BGR (標準匹配)
    res_bgr = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
    _, val_bgr, _, loc_bgr = cv2.minMaxLoc(res_bgr)
    # 將座標轉換回原圖座標
    center_bgr = (x1 + loc_bgr[0] + template.shape[1]//2, y1 + loc_bgr[1] + template.shape[0]//2)
    
    # Method 2: Masked
    gray_tpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray_tpl, 160, 255, cv2.THRESH_BINARY)
    res_mask = cv2.matchTemplate(search_area, template, cv2.TM_CCORR_NORMED, mask=mask)
    _, val_mask, _, loc_mask = cv2.minMaxLoc(res_mask)
    center_mask = (x1 + loc_mask[0] + template.shape[1]//2, y1 + loc_mask[1] + template.shape[0]//2)

    print(f"  BGR: {val_bgr:.2%}, Center: {center_bgr}")
    print(f"  Masked: {val_mask:.2%}, Center: {center_mask}")

    # 畫圖
    out = screenshot.copy()
    # 畫 ROI 範圍 (藍色)
    cv2.rectangle(out, (x1, y1), (x2, y2), (255, 0, 0), 2)
    
    # BGR - 紅圈
    cv2.circle(out, center_bgr, 15, (0, 0, 255), 3)
    cv2.putText(out, f"BGR: {val_bgr:.2%}", (center_bgr[0]+20, center_bgr[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    
    # Masked - 綠框
    tl_mask = (x1 + loc_mask[0], y1 + loc_mask[1])
    cv2.rectangle(out, tl_mask, (tl_mask[0]+template.shape[1], tl_mask[1]+template.shape[0]), (0, 255, 0), 2)
    cv2.putText(out, f"Masked: {val_mask:.2%}", (tl_mask[0], tl_mask[1]-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    cv2.imwrite(f"D:/Project/wvd/test/{output_name}.png", out)
    print(f"  Saved to {output_name}.png")

if __name__ == "__main__":
    t = "D:/Project/wvd/test/template.png"
    roi = [95, 971, 799, 1136]  # x1, y1, x2, y2
    
    find_with_roi(t, "D:/Project/wvd/test/screenshot_original.png", roi, "match_roi_original")
    find_with_roi(t, "D:/Project/wvd/test/1.png", roi, "match_roi_1")
