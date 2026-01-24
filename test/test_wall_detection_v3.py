"""
牆壁偵測 v3 - 使用連通區域分析 + 邊界觸碰偵測
"""
import cv2
import numpy as np
from pathlib import Path

def match_template_in_roi(screenshot_path, template_path, template_name):
    screenshot = cv2.imread(str(screenshot_path))
    template = cv2.imread(str(template_path), cv2.IMREAD_UNCHANGED)
    
    if screenshot is None or template is None:
        return None
    
    h, w = screenshot.shape[:2]
    roi_x, roi_y = w // 2, 0
    roi_w, roi_h = w // 2, h // 2
    roi = screenshot[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w]
    
    if template.shape[2] == 4:
        res = cv2.matchTemplate(roi, template[:,:,:3], cv2.TM_CCORR_NORMED, mask=template[:,:,3])
    else:
        res = cv2.matchTemplate(roi, template, cv2.TM_CCORR_NORMED)
        
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val < 0.7: return None
    
    return {
        "pos": (roi_x + max_loc[0], roi_y + max_loc[1]),
        "size": (template.shape[1], template.shape[0]),
        "img": screenshot,
        "name": template_name
    }

def detect_walls_connected(screenshot, arrow_pos, arrow_size):
    """
    使用連通區域分析偵測牆壁
    只有「連續的白線」且「觸碰到邊界」才會被判定為牆壁
    """
    ax, ay = arrow_pos
    aw, ah = arrow_size
    cx, cy = ax + aw // 2, ay + ah // 2
    
    # 偵測範圍：箭頭最大邊長 + 50 像素 (大幅擴大確保包含牆壁)
    side = max(aw, ah) + 50
    r = side // 2
    
    x1, y1 = max(0, cx - r), max(0, cy - r)
    x2, y2 = min(screenshot.shape[1], cx + r), min(screenshot.shape[0], cy + r)
    roi = screenshot[y1:y2, x1:x2]
    
    # --- HSV 白色偵測 (放寬亮度門檻以抓到較暗的白線) ---
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    # V > 160 (放寬), S < 60 (稍放寬)
    lower_white = np.array([0, 0, 160], dtype=np.uint8)
    upper_white = np.array([180, 60, 255], dtype=np.uint8)
    white_mask = cv2.inRange(hsv, lower_white, upper_white)
    
    # 扣除箭頭區域
    arrow_mask = np.zeros_like(white_mask)
    rax1, ray1 = max(0, ax - x1), max(0, ay - y1)
    rax2, ray2 = min(roi.shape[1], rax1 + aw), min(roi.shape[0], ray1 + ah)
    arrow_mask[ray1:ray2, rax1:rax2] = 255
    white_outside = cv2.bitwise_and(white_mask, cv2.bitwise_not(arrow_mask))
    
    h, w = white_outside.shape
    
    # --- 連通區域分析：檢查區域內是否存在「足夠長且形狀正確」的白線 ---
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(white_outside, connectivity=8)
    
    h, w = white_outside.shape
    # 計算箭頭在 ROI 中的相對位置
    arrow_cx = rax1 + aw // 2
    arrow_cy = ray1 + ah // 2
    
    # 長度門檻：白線需要超過這個長度才算牆
    MIN_WALL_LENGTH = 20
    
    results = {"上方": False, "下方": False, "左方": False, "右方": False}
    details = {"上方": 0, "下方": 0, "左方": 0, "右方": 0}
    
    for i in range(1, num_labels):  # 0 是背景
        area = stats[i, cv2.CC_STAT_AREA]
        comp_w = stats[i, cv2.CC_STAT_WIDTH]   # 連通區域的寬度
        comp_h = stats[i, cv2.CC_STAT_HEIGHT]  # 連通區域的高度
        
        if area < 15:  # 過濾太小的雜點
            continue
        
        # 取得該連通區域的中心點
        comp_cx, comp_cy = centroids[i]
        
        # 判斷這個白線區域在箭頭的哪個方向
        # 使用形狀比例判斷：
        # - 橫向牆壁 (上/下)：寬度 >= 高度 * 1.5 且 寬度 >= MIN_WALL_LENGTH
        # - 縱向牆壁 (左/右)：高度 >= 寬度 * 1.5 且 高度 >= MIN_WALL_LENGTH
        
        is_horizontal = comp_w >= comp_h * 1.5 and comp_w >= MIN_WALL_LENGTH
        is_vertical = comp_h >= comp_w * 1.5 and comp_h >= MIN_WALL_LENGTH
        
        # 上方區域：白線在箭頭上方，且是橫向線條
        if comp_cy < ray1 and is_horizontal:
            results["上方"] = True
            details["上方"] = max(details["上方"], comp_w)
        # 下方區域：白線在箭頭下方，且是橫向線條
        if comp_cy > ray2 and is_horizontal:
            results["下方"] = True
            details["下方"] = max(details["下方"], comp_w)
        # 左方區域：白線在箭頭左方，且是縱向線條
        if comp_cx < rax1 and is_vertical:
            results["左方"] = True
            details["左方"] = max(details["左方"], comp_h)
        # 右方區域：白線在箭頭右方，且是縱向線條
        if comp_cx > rax2 and is_vertical:
            results["右方"] = True
            details["右方"] = max(details["右方"], comp_h)
    
    stat = {
        "arrow_white_count": np.sum(cv2.bitwise_and(white_mask, arrow_mask) == 255),
        "outside_white_count": np.sum(white_outside == 255),
        "connected_components": num_labels - 1
    }
            
    return results, (x1, y1, x2, y2), white_outside, details, stat

def main():
    test_dir = Path(r"D:\Project\wvd\test")
    output_dir = test_dir / "wall_detection_results"
    output_dir.mkdir(exist_ok=True)
    
    screenshots = sorted((test_dir / "screenshot").glob("*.png"))
    templates = [(test_dir / "temple" / f"{i}.png", f"A{i}") for i in [1, 2, 3]]
    
    print("=" * 60)
    print("牆壁偵測 v3 - 連通區域 + 邊界觸碰分析")
    print("=" * 60)
    
    for sc_path in screenshots:
        print(f"\n📸 圖片: {sc_path.name}")
        matches = []
        for t_path, t_name in templates:
            m = match_template_in_roi(sc_path, t_path, t_name)
            if m:
                screenshot = cv2.imread(str(sc_path))
                roi_x = screenshot.shape[1] // 2
                roi = screenshot[0:screenshot.shape[0]//2, roi_x:]
                template = cv2.imread(str(t_path), cv2.IMREAD_UNCHANGED)
                if template.shape[2] == 4:
                    res = cv2.matchTemplate(roi, template[:,:,:3], cv2.TM_CCORR_NORMED, mask=template[:,:,3])
                else:
                    res = cv2.matchTemplate(roi, template, cv2.TM_CCORR_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                m["conf"] = max_val
                matches.append(m)
        
        match = max(matches, key=lambda x: x["conf"]) if matches else None
        
        if match:
            walls, box, mask, detail, stat = detect_walls_connected(match["img"], match["pos"], match["size"])
            
            res_img = match["img"].copy()
            x1, y1, x2, y2 = box
            ax, ay = match["pos"]
            aw, ah = match["size"]
            
            # 獲取 ROI 並標記
            roi = res_img[y1:y2, x1:x2]
            gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            _, white_total = cv2.threshold(gray_roi, 180, 255, cv2.THRESH_BINARY)
            
            # 重新計算 mask 用於著色
            lower_white = np.array([0, 0, 180], dtype=np.uint8)
            upper_white = np.array([180, 50, 255], dtype=np.uint8)
            white_mask_roi = cv2.inRange(hsv_roi, lower_white, upper_white)
            
            arrow_mask = np.zeros_like(white_mask_roi)
            rax1, ray1 = max(0, ax - x1), max(0, ay - y1)
            rax2, ray2 = min(roi.shape[1], rax1 + aw), min(roi.shape[0], ray1 + ah)
            arrow_mask[ray1:ray2, rax1:rax2] = 255
            
            white_in_arrow = cv2.bitwise_and(white_mask_roi, arrow_mask)
            white_outside_arrow = cv2.bitwise_and(white_mask_roi, cv2.bitwise_not(arrow_mask))
            
            # 著色
            roi[white_outside_arrow == 255] = [0, 0, 255]  # 紅色=牆壁
            roi[white_in_arrow == 255] = [255, 0, 0]       # 藍色=箭頭內
            
            # 繪製邊框
            cv2.rectangle(res_img, (x1, y1), (x2, y2), (255, 255, 255), 2)
            cv2.rectangle(res_img, (ax, ay), (ax + aw, ay + ah), (0, 255, 0), 1)
            
            print(f"  📍 箭頭: {match['pos']}, 尺寸: {match['size']}")
            print(f"  📏 偵測框: {x2-x1}x{y2-y1}, 連通區域數: {stat['connected_components']}")
            print(f"  ⚪ 白色像素: 箭頭內({stat['arrow_white_count']}) vs 箭頭外({stat['outside_white_count']})")
            print("  🧱 牆壁偵測 (連通區域觸碰邊界):")
            for d in ["上方", "下方", "左方", "右方"]:
                status = "🚫 牆" if walls[d] else "✅ 通"
                print(f"     {d}: {status}")
            
            cv2.imwrite(str(output_dir / f"wall_{sc_path.name}"), res_img)
            cv2.imwrite(str(output_dir / f"mask_{sc_path.name}"), mask)
        else:
            print("  ❌ 沒找到箭頭")

    print("\n" + "=" * 60)
    print(f"結果已保存至: {output_dir}")

if __name__ == "__main__":
    main()
