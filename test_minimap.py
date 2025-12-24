"""
小地圖樓梯偵測測試腳本
用於測試圖片匹配是否正常工作
"""
import cv2
import numpy as np
import os

# 設定路徑
SCREENSHOT_PATH = r"d:\Project\wvd\MuMu-20251224-124829-177.png"
TEMPLATE_PATH = r"d:\Project\wvd\resources\images\DH-R5-minimap.png"

# 小地圖 ROI: 左上角(651,24) 右下角(870,244)
MINIMAP_ROI = [651, 24, 219, 220]  # [x, y, width, height]

def test_minimap_detection():
    print("=== 小地圖樓梯偵測測試 ===\n")
    
    # 1. 載入圖片
    print("1. 載入圖片...")
    screenshot = cv2.imread(SCREENSHOT_PATH)
    template = cv2.imread(TEMPLATE_PATH)
    
    if screenshot is None:
        print(f"   ❌ 無法載入截圖: {SCREENSHOT_PATH}")
        return
    print(f"   ✓ 截圖尺寸: {screenshot.shape}")
    
    if template is None:
        print(f"   ❌ 無法載入模板: {TEMPLATE_PATH}")
        return
    print(f"   ✓ 模板尺寸: {template.shape}")
    
    # 2. 裁剪小地圖區域
    print("\n2. 裁剪小地圖區域...")
    x, y, w, h = MINIMAP_ROI
    print(f"   ROI: x={x}, y={y}, w={w}, h={h}")
    
    # 確保不超出邊界
    img_h, img_w = screenshot.shape[:2]
    x_end = min(x + w, img_w)
    y_end = min(y + h, img_h)
    
    minimap_area = screenshot[y:y_end, x:x_end].copy()
    print(f"   ✓ 小地圖區域尺寸: {minimap_area.shape}")
    
    # 儲存小地圖區域供檢查
    cv2.imwrite("debug_minimap_area.png", minimap_area)
    print(f"   ✓ 已儲存 debug_minimap_area.png")
    
    # 3. 檢查模板是否可以放入小地圖區域
    print("\n3. 檢查模板與搜索區域...")
    templ_h, templ_w = template.shape[:2]
    area_h, area_w = minimap_area.shape[:2]
    
    print(f"   模板尺寸: {templ_w} x {templ_h}")
    print(f"   搜索區域: {area_w} x {area_h}")
    
    if templ_w > area_w or templ_h > area_h:
        print(f"   ❌ 模板太大！無法在搜索區域中找到")
        print(f"   建議：縮小模板圖片，或調整 ROI 範圍")
        return
    
    print(f"   ✓ 模板可以放入搜索區域")
    
    # 4. 執行模板匹配
    print("\n4. 執行模板匹配...")
    result = cv2.matchTemplate(minimap_area, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
    
    print(f"   最大匹配度: {max_val * 100:.2f}%")
    print(f"   最佳匹配位置: {max_loc}")
    
    threshold = 0.80
    if max_val >= threshold:
        print(f"   ✓ 匹配成功！超過閾值 {threshold * 100:.0f}%")
    else:
        print(f"   ❌ 匹配失敗！未達閾值 {threshold * 100:.0f}%")
    
    # 5. 在原圖上標記匹配位置
    print("\n5. 生成偵錯圖片...")
    
    # 在小地圖區域上標記匹配位置
    debug_minimap = minimap_area.copy()
    cv2.rectangle(debug_minimap, 
                  max_loc, 
                  (max_loc[0] + templ_w, max_loc[1] + templ_h), 
                  (0, 255, 0) if max_val >= threshold else (0, 0, 255), 
                  2)
    cv2.imwrite("debug_minimap_match.png", debug_minimap)
    print(f"   ✓ 已儲存 debug_minimap_match.png（小地圖區域標記）")
    
    # 在原截圖上標記 ROI 和匹配位置
    debug_full = screenshot.copy()
    # 標記 ROI
    cv2.rectangle(debug_full, (x, y), (x_end, y_end), (255, 255, 0), 2)
    cv2.putText(debug_full, "Minimap ROI", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
    # 標記匹配位置（需要加上 ROI 偏移）
    match_x = x + max_loc[0]
    match_y = y + max_loc[1]
    cv2.rectangle(debug_full, 
                  (match_x, match_y), 
                  (match_x + templ_w, match_y + templ_h), 
                  (0, 255, 0) if max_val >= threshold else (0, 0, 255), 
                  2)
    cv2.imwrite("debug_full_screenshot.png", debug_full)
    print(f"   ✓ 已儲存 debug_full_screenshot.png（完整截圖標記）")
    
    # 6. 額外測試：在整個螢幕上搜索
    print("\n6. 額外測試：在整個螢幕上搜索...")
    result_full = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
    _, max_val_full, _, max_loc_full = cv2.minMaxLoc(result_full)
    print(f"   全螢幕最大匹配度: {max_val_full * 100:.2f}%")
    print(f"   全螢幕最佳匹配位置: {max_loc_full}")
    
    if max_val_full >= threshold:
        print(f"   ✓ 全螢幕匹配成功！")
        if max_loc_full[0] < x or max_loc_full[0] > x_end or max_loc_full[1] < y or max_loc_full[1] > y_end:
            print(f"   ⚠️ 但位置不在 ROI 範圍內！請檢查 ROI 設定")
    
    print("\n=== 測試完成 ===")
    print("\n偵錯檔案：")
    print("  - debug_minimap_area.png: 裁剪的小地圖區域")
    print("  - debug_minimap_match.png: 小地圖區域匹配結果")
    print("  - debug_full_screenshot.png: 完整截圖標記")

if __name__ == "__main__":
    test_minimap_detection()
