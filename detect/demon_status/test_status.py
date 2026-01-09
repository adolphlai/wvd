import cv2
import numpy as np
import os

# 角色狀態偵測區域定義 (x, y, w, h)
# 使用者提供座標為 [x1 y1, x2 y2]
# 角色 0: [137 1234, 299 1279] -> x=137, y=1234, w=162, h=45
# 角色 1: [420 1234, 585 1279] -> x=420, y=1234, w=165, h=45
# 角色 2: [704 1234, 871 1279] -> x=704, y=1234, w=167, h=45
# 角色 3: [137 1410, 299 1461] -> x=137, y=1410, w=162, h=51
# 角色 4: [420 1410, 585 1461] -> x=420, y=1410, w=165, h=51
# 角色 5: [704 1410, 871 1461] -> x=704, y=1410, w=167, h=51

ROIS = [
    (137, 1234, 162, 45),  # Character 0
    (420, 1234, 165, 45),  # Character 1
    (704, 1234, 167, 45),  # Character 2
    (137, 1410, 162, 51),  # Character 3
    (420, 1410, 165, 51),  # Character 4
    (704, 1410, 167, 51),  # Character 5
]

def load_image(path):
    """讀取圖片，支援中文路徑"""
    try:
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return None

def main():
    base_dir = r"D:\Project\wvd\detect\demon_status"
    template_path = os.path.join(base_dir, "cursed_icon.png")
    
    # 載入模板
    template = load_image(template_path)
    if template is None:
        print(f"Failed to load template: {template_path}")
        return

    # 取得測試圖片
    test_images = [f"demon{i}.png" for i in range(1, 6)]
    test_images.append("cursed.png")

    print(f"{'Image':<15} | {'Char':<4} | {'Match %':<8} | {'Red Px':<6} | {'Status'}")
    print("-" * 55)

    for img_name in test_images:
        img_path = os.path.join(base_dir, img_name)
        screen = load_image(img_path)
        if screen is None:
            continue

        for i, (x, y, w, h) in enumerate(ROIS):
            # 裁切區域
            crop = screen[y:y+h, x:x+w]
            
            # 顏色分析 (紅像素)
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            lower_red1 = np.array([0, 100, 100])
            upper_red1 = np.array([10, 255, 255])
            lower_red2 = np.array([160, 100, 100])
            upper_red2 = np.array([180, 255, 255])
            mask = cv2.bitwise_or(cv2.inRange(hsv, lower_red1, upper_red1), 
                                cv2.inRange(hsv, lower_red2, upper_red2))
            red_pixels = cv2.countNonZero(mask)

            # 模板匹配
            result = cv2.matchTemplate(crop, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            
            match_pct = max_val * 100
            # 降低門檻到 70% 以便觀察邊界情況
            status = "DETECTED" if match_pct >= 70 else "-"
            
            print(f"{img_name:<15} | {i:<4} | {match_pct:>6.2f}% | {red_pixels:>6} | {status}")

            # 如果匹配度高，繪製框線以便驗證
            if match_pct >= 70:
                top_left = (x + max_loc[0], y + max_loc[1])
                bottom_right = (top_left[0] + template.shape[1], top_left[1] + template.shape[0])
                cv2.rectangle(screen, top_left, bottom_right, (0, 255, 0), 2)
                cv2.putText(screen, f"C{i}:{match_pct:.0f}%", (x, y-5), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        # 儲存結果圖片以便人工驗證位置
        output_name = f"result_{img_name}"
        output_path = os.path.join(base_dir, output_name)
        cv2.imencode('.png', screen)[1].tofile(output_path)

if __name__ == "__main__":
    main()
