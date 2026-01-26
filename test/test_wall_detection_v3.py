"""
牆壁偵測 v3 - 使用連通區域分析 + 形狀比例判斷
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
    採用區域內存在白線之偵測邏輯，並加入形狀比例判斷
    """
    ax, ay = arrow_pos
    aw, ah = arrow_size
    cx, cy = ax + aw // 2, ay + ah // 2
    
    # 偵測範圍：擴大至箭頭最大邊長 + 30 像素 (避免邊緣牆壁被切掉)
    side = max(aw, ah) + 30
    r = side // 2
    
    x1, y1 = max(0, cx - r), max(0, cy - r)
    x2, y2 = min(screenshot.shape[1], cx + r), min(screenshot.shape[0], cy + r)
    roi = screenshot[y1:y2, x1:x2]
    
    # --- HSV 白色偵測 (基準門檻：V=160) ---
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower_white = np.array([0, 0, 160], dtype=np.uint8)
    upper_white = np.array([180, 60, 255], dtype=np.uint8)
    white_mask = cv2.inRange(hsv, lower_white, upper_white)
    
    # 扣除箭頭區域
    arrow_mask = np.zeros_like(white_mask)
    rax1, ray1 = max(0, ax - x1), max(0, ay - y1)
    rax2, ray2 = min(roi.shape[1], rax1 + aw), min(roi.shape[0], ray1 + ah)
    arrow_mask[ray1:ray2, rax1:rax2] = 255
    white_outside = cv2.bitwise_and(white_mask, cv2.bitwise_not(arrow_mask))
    
    # --- 雜訊過濾 ---
    kernel = np.ones((2, 2), np.uint8)
    white_outside = cv2.morphologyEx(white_outside, cv2.MORPH_OPEN, kernel, iterations=1)
    
    # --- 區域內幾何特徵判定 (Intra-Zone Geometry Check) ---
    results = {"上方": False, "下方": False, "左方": False, "右方": False}
    details = {"上方": 0, "下方": 0, "左方": 0, "右方": 0}
    
    # 判定與箭頭同寬/高的偵測軌道
    zones = {
        "上方": white_outside[0:ray1, rax1:rax2],
        "下方": white_outside[ray2:white_outside.shape[0], rax1:rax2],
        "左方": white_outside[ray1:ray2, 0:rax1],
        "右方": white_outside[ray1:ray2, rax2:white_outside.shape[1]]
    }
    
    MIN_DIM = 10
    
    for side, zone_img in zones.items():
        if zone_img.size == 0: continue
        num, labels, stats, _ = cv2.connectedComponentsWithStats(zone_img, connectivity=8)
        
        for i in range(1, num):
            w = stats[i, cv2.CC_STAT_WIDTH]
            h = stats[i, cv2.CC_STAT_HEIGHT]
            area = stats[i, cv2.CC_STAT_AREA]
            
            if area < 10: continue
            
            # 方位一致性判定
            if side in ["上方", "下方"]:
                # 橫向軌道：應具備橫向特徵 (寬度大於高度，且寬度足夠)
                if w >= h * 0.7 and w >= MIN_DIM:
                    results[side] = True
                    details[side] = max(details[side], w)
            else:
                # 縱向軌道：應具備縱向特徵 (高度大於寬度，且高度足夠)
                if h >= w * 0.7 and h >= MIN_DIM:
                    results[side] = True
                    details[side] = max(details[side], h)
    
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(white_outside, connectivity=8)
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
    print("牆壁偵測 v3 - 連通區域 + 形狀比例判斷")
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
            
            roi = res_img[y1:y2, x1:x2]
            hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            lower_white = np.array([0, 0, 160], dtype=np.uint8)
            upper_white = np.array([180, 60, 255], dtype=np.uint8)
            white_mask_roi = cv2.inRange(hsv_roi, lower_white, upper_white)
            
            arrow_mask = np.zeros_like(white_mask_roi)
            rax1, ray1 = max(0, ax - x1), max(0, ay - y1)
            rax2, ray2 = min(roi.shape[1], rax1 + aw), min(roi.shape[0], ray1 + ah)
            arrow_mask[ray1:ray2, rax1:rax2] = 255
            
            white_in_arrow = cv2.bitwise_and(white_mask_roi, arrow_mask)
            white_outside_arrow = cv2.bitwise_and(white_mask_roi, cv2.bitwise_not(arrow_mask))
            
            roi[white_outside_arrow == 255] = [0, 0, 255]
            roi[white_in_arrow == 255] = [255, 0, 0]
            
            cv2.rectangle(res_img, (x1, y1), (x2, y2), (255, 255, 255), 2)
            cv2.rectangle(res_img, (ax, ay), (ax + aw, ay + ah), (0, 255, 0), 1)
            
            print(f"  📍 箭頭: {match['pos']}")
            print("  🧱 牆壁偵測:")
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
