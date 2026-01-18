import cv2
import numpy as np
import os

def clean_template(tpl_path):
    """
    手動去背：提取模板中的亮色文字，並將背景設為純黑，同時生成遮罩
    """
    img = cv2.imread(tpl_path)
    if img is None: return None, None
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # 提取文字部分 (門檻 130 比較保險)
    _, mask = cv2.threshold(gray, 130, 255, cv2.THRESH_BINARY)
    
    # 將背景完全塗黑，只留文字
    clean_img = cv2.bitwise_and(img, cv2.merge([mask, mask, mask]))
    
    return clean_img, mask

def process_ultimate_matching(screenshot_dir, template_dir, output_dir, roi):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    screenshots = [f for f in os.listdir(screenshot_dir) if f.endswith('.png')]
    templates = [f for f in os.listdir(template_dir) if f.endswith('.png')]
    
    tpl_data = []
    for t_name in templates:
        path = os.path.join(template_dir, t_name)
        clean_img, mask = clean_template(path)
        if clean_img is None: continue
        tpl_data.append({
            'name': t_name,
            'clean': clean_img,
            'mask': mask
        })
    
    x1, y1, x2, y2 = roi
    print(f"Executing Ultimate Masked Matching (TM_CCOEFF_NORMED with Mask)...")

    for s_name in screenshots:
        s_path = os.path.join(screenshot_dir, s_name)
        orig_img = cv2.imread(s_path)
        if orig_img is None: continue
        
        search_roi = orig_img[y1:y2, x1:x2]
        canvas = orig_img.copy()
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (255, 100, 0), 2)
        
        for t_idx, t_info in enumerate(tpl_data):
            # TM_CCOEFF_NORMED 配合遮罩是目前 OpenCV 最強的去背比對方案
            try:
                res = cv2.matchTemplate(search_roi, t_info['clean'], cv2.TM_CCOEFF_NORMED, mask=t_info['mask'])
                _, val, _, loc = cv2.minMaxLoc(res)
            except Exception as e:
                # 如果 OpenCV 版本太舊不支援 CCOEFF+MASK，會跳到這裡
                print(f"Warning: OpenCV version mismatch for masked CCOEFF: {e}")
                continue

            tw, th = t_info['clean'].shape[1], t_info['clean'].shape[0]
            cx = x1 + loc[0] + tw // 2
            cy = y1 + loc[1] + th // 2
            
            color = (0, 0, 255) if t_idx == 0 else (0, 255, 0)
            
            # 使用 Mask 之後，匹配度門檻設在 0.7 左右就非常精準
            if val > 0.70:
                cv2.circle(canvas, (cx, cy), 15, color, 2)
                cv2.line(canvas, (cx-15, cy), (cx+15, cy), color, 2)
                cv2.line(canvas, (cx, cy-15), (cx, cy+15), color, 2)
                label = f"MATCH: {t_info['name']} ({val:.2%})"
            else:
                label = f"FAIL: {t_info['name']} ({val:.2%})"
            
            cv2.putText(canvas, label, (x1, y1 - 10 - t_idx*25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
        out_path = os.path.join(output_dir, f"ultimate_{s_name}")
        cv2.imwrite(out_path, canvas)
        print(f"  Result saved: ultimate_{s_name}")

if __name__ == "__main__":
    SCREENSHOT_DIR = "D:/Project/wvd/test/screenshot"
    TEMPLATE_DIR = "D:/Project/wvd/test/temple"
    RESULT_DIR = "D:/Project/wvd/test/resulty"
    ROI = [95, 971, 799, 1136]
    process_ultimate_matching(SCREENSHOT_DIR, TEMPLATE_DIR, RESULT_DIR, ROI)
