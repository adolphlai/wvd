import cv2
import numpy as np
import os

def process_binary_matching(screenshot_dir, template_dir, output_dir, roi):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    screenshots = [f for f in os.listdir(screenshot_dir) if f.endswith('.png')]
    templates = [f for f in os.listdir(template_dir) if f.endswith('.png')]
    
    tpl_data = []
    for t_name in templates:
        path = os.path.join(template_dir, t_name)
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None: continue
        # 二值化模板
        _, thr = cv2.threshold(img, 150, 255, cv2.THRESH_BINARY)
        tpl_data.append({
            'name': t_name,
            'thr': thr
        })
        
    x1, y1, x2, y2 = roi
    
    print(f"Executing Binary Matching (True BG Removal)...")
    
    for s_name in screenshots:
        s_path = os.path.join(screenshot_dir, s_name)
        orig_img = cv2.imread(s_path)
        if orig_img is None: continue
        
        search_roi = orig_img[y1:y2, x1:x2]
        gray_roi = cv2.cvtColor(search_roi, cv2.COLOR_BGR2GRAY)
        # 對搜尋區域也進行二值化，徹底去除背景色塊
        _, thr_roi = cv2.threshold(gray_roi, 160, 255, cv2.THRESH_BINARY)
        
        canvas = orig_img.copy()
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (255, 100, 0), 2)
        
        for t_idx, t_info in enumerate(tpl_data):
            # 在二值化圖像上進行傳統匹配
            res = cv2.matchTemplate(thr_roi, t_info['thr'], cv2.TM_CCOEFF_NORMED)
            _, val, _, loc = cv2.minMaxLoc(res)
            
            tw, th = t_info['thr'].shape[1], t_info['thr'].shape[0]
            cx = x1 + loc[0] + tw // 2
            cy = y1 + loc[1] + th // 2
            
            color = (0, 0, 255) if t_idx == 0 else (0, 255, 0)
            
            # 二值化匹配的門檻通常在 0.6~0.8
            if val > 0.65:
                cv2.circle(canvas, (cx, cy), 15, color, 2)
                cv2.line(canvas, (cx-10, cy-10), (cx+10, cy+10), color, 2)
                cv2.line(canvas, (cx-10, cy+10), (cx+10, cy-10), color, 2)
                label = f"FOUND {t_info['name']}: {val:.2%}"
            else:
                label = f"MISS {t_info['name']}: {val:.2%}"
            
            cv2.putText(canvas, label, (x1, y1 - 10 - t_idx*25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
        out_path = os.path.join(output_dir, f"binary_{s_name}")
        cv2.imwrite(out_path, canvas)
        print(f"  Generated result: binary_{s_name}")

if __name__ == "__main__":
    SCREENSHOT_DIR = "D:/Project/wvd/test/screenshot"
    TEMPLATE_DIR = "D:/Project/wvd/test/temple"
    RESULT_DIR = "D:/Project/wvd/test/resulty"
    ROI = [95, 971, 799, 1136]
    process_binary_matching(SCREENSHOT_DIR, TEMPLATE_DIR, RESULT_DIR, ROI)
