import cv2
import numpy as np
import os

# 角色狀態偵測區域定義 (x, y, w, h)
ROIS = [
    (137, 1230, 162, 60),  # Character 0
    (420, 1230, 165, 60),  # Character 1
    (704, 1230, 167, 60),  # Character 2
    (137, 1405, 162, 60),  # Character 3
    (420, 1405, 165, 60),  # Character 4
    (704, 1405, 167, 60),  # Character 5
]

def load_image(path):
    """讀取圖片，支援中文路徑"""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return None

def main():
    base_dir = r"D:\Project\wvd\detect\麻痺"
    template_path = os.path.join(base_dir, "paralysis_icon.png")
    
    # 載入模板
    template = load_image(template_path)
    if template is None:
        print(f"Failed to load template: {template_path}")
        return

    # 取得測試圖片
    test_images = [f"paralysis{i}.png" for i in range(1, 4)]

    print(f"{'Image':<15} | {'Char':<4} | {'Match %':<8} | {'Status'}")
    print("-" * 50)

    for img_name in test_images:
        img_path = os.path.join(base_dir, img_name)
        screen = load_image(img_path)
        if screen is None:
            continue

        for i, (x, y, w, h) in enumerate(ROIS):
            # 確保 ROI 在圖片範圍內
            if y + h > screen.shape[0] or x + w > screen.shape[1]:
                continue
                
            # 裁切區域
            crop = screen[y:y+h, x:x+w]
            
            # 模板匹配
            result = cv2.matchTemplate(crop, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            
            match_pct = max_val * 100
            # 使用建議的 75% 作為門檻
            status = "DETECTED" if match_pct >= 75 else "-"
            
            print(f"{img_name:<15} | {i:<4} | {match_pct:>6.2f}% | {status}")

            # 視覺化
            if match_pct >= 60: # 稍微放寬視覺化門檻以便觀察
                top_left = (x + max_loc[0], y + max_loc[1])
                bottom_right = (top_left[0] + template.shape[1], top_left[1] + template.shape[0])
                color = (0, 255, 255) if match_pct >= 75 else (0, 165, 255)
                cv2.rectangle(screen, top_left, bottom_right, color, 2)
                cv2.putText(screen, f"P{i}:{match_pct:.0f}%", (x, y-5), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        # 儲存結果圖片
        output_name = f"result_{img_name}"
        output_path = os.path.join(base_dir, output_name)
        cv2.imencode('.png', screen)[1].tofile(output_path)

if __name__ == "__main__":
    main()
