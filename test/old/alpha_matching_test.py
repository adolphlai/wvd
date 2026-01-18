import cv2
import numpy as np
import os

def create_transparent_mask(template_img):
    """
    將模板圖片轉換為帶有透明背景的文字遮罩
    """
    gray = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)
    # 提取亮色文字 (門檻 150)
    _, mask = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    
    # 稍微膨脹遮罩以包含文字邊緣的消除鋸齒部分
    kernel = np.ones((2,2), np.uint8)
    mask = cv2.dilate(mask, kernel, iterations=1)
    
    return mask

def process_alpha_matching(screenshot_dir, template_dir, output_dir, roi):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    screenshots = [f for f in os.listdir(screenshot_dir) if f.endswith('.png')]
    templates = [f for f in os.listdir(template_dir) if f.endswith('.png')]
    
    tpl_data = []
    for t_name in templates:
        path = os.path.join(template_dir, t_name)
        img = cv2.imread(path)
        if img is None: continue
        mask = create_transparent_mask(img)
        tpl_data.append({
            'name': t_name,
            'orig': img,
            'mask': mask
        })
        
    x1, y1, x2, y2 = roi
    
    print(f"Executing Alpha-Mask Matching... Templates: {[t['name'] for t in tpl_data]}")
    
    for s_name in screenshots:
        s_path = os.path.join(screenshot_dir, s_name)
        canvas = cv2.imread(s_path)
        if canvas is None: continue
        
        search_roi = canvas[y1:y2, x1:x2]
        
        # 畫 ROI 框
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (255, 100, 0), 2)
        
        for t_idx, t_info in enumerate(tpl_data):
            # 使用 TM_CCORR_NORMED 配合 mask 效果最好
            # 注意：帶 mask 只能用 TM_SQDIFF 或 TM_CCORR_NORMED
            res = cv2.matchTemplate(search_roi, t_info['orig'], cv2.TM_CCORR_NORMED, mask=t_info['mask'])
            _, val, _, loc = cv2.minMaxLoc(res)
            
            tw, th = t_info['orig'].shape[1], t_info['orig'].shape[0]
            cx = x1 + loc[0] + tw // 2
            cy = y1 + loc[1] + th // 2
            
            color = (0, 0, 255) if t_idx == 0 else (0, 255, 0)
            
            # 只有當匹配度極高時才認為找到了 (帶 Mask 匹配通常分數很高，需 > 0.99)
            if val > 0.99:
                # 畫十字標記
                cv2.line(canvas, (cx - 20, cy), (cx + 20, cy), color, 2)
                cv2.line(canvas, (cx, cy - 20), (cx, cy + 20), color, 2)
                cv2.circle(canvas, (cx, cy), 15, color, 2)
                label = f"FOUND {t_info['name']}: {val:.4f}"
            else:
                label = f"MISS {t_info['name']}: {val:.4f}"
            
            cv2.putText(canvas, label, (x1, y1 - 10 - t_idx*25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
        out_path = os.path.join(output_dir, f"alpha_{s_name}")
        cv2.imwrite(out_path, canvas)
        print(f"  Generated result: alpha_{s_name}")

if __name__ == "__main__":
    SCREENSHOT_DIR = "D:/Project/wvd/test/screenshot"
    TEMPLATE_DIR = "D:/Project/wvd/test/temple"
    RESULT_DIR = "D:/Project/wvd/test/resulty"
    ROI = [95, 971, 799, 1136]
    
    process_alpha_matching(SCREENSHOT_DIR, TEMPLATE_DIR, RESULT_DIR, ROI)
