import cv2
import numpy as np
import os

def process_final_matching(screenshot_dir, template_dir, output_dir, roi):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    screenshots = [f for f in os.listdir(screenshot_dir) if f.endswith('.png')]
    # 自動尋找所有產出的去背模板
    templates = [f for f in os.listdir(template_dir) if f.endswith('_clean.png')]
    print(f"Found {len(templates)} clean templates: {', '.join(templates)}")
    
    tpl_data = []
    for t_name in templates:
        path = os.path.join(template_dir, t_name)
        # 讀取帶 Alpha 通道的圖
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None: continue
        
        # 提取 BGR 部分
        bgr = img[:, :, :3]
        # 提取 Alpha 部分作為遮罩
        mask = img[:, :, 3]
        
        tpl_data.append({
            'name': t_name,
            'bgr': bgr,
            'mask': mask
        })
    
    x1, y1, x2, y2 = roi
    print(f"Executing Final Precise Matching with Clean Templates...")

    for s_name in screenshots:
        s_path = os.path.join(screenshot_dir, s_name)
        orig_img = cv2.imread(s_path)
        if orig_img is None: continue
        
        search_roi = orig_img[y1:y2, x1:x2]
        canvas = orig_img.copy()
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (255, 100, 0), 2)
        
        for t_idx, t_info in enumerate(tpl_data):
            try:
                # 使用去背後的 BGR + Alpha Mask 進行 CCOEFF 比對
                res = cv2.matchTemplate(search_roi, t_info['bgr'], cv2.TM_CCOEFF_NORMED, mask=t_info['mask'])
                _, val, _, loc = cv2.minMaxLoc(res)
            except Exception as e:
                print(f"Error: {e}")
                continue

            tw, th = t_info['bgr'].shape[1], t_info['bgr'].shape[0]
            cx = x1 + loc[0] + tw // 2
            cy = y1 + loc[1] + th // 2
            
            # Colors for different templates
            colors = [(0, 0, 255), (0, 255, 0), (255, 0, 0), (0, 255, 255), (255, 0, 255)]
            color = colors[t_idx % len(colors)]
            
            # 手動去背後，門檻 70% 以上即為絕對匹配
            if val > 0.70:
                cv2.circle(canvas, (cx, cy), 18, color, 3)
                cv2.line(canvas, (cx-20, cy), (cx+20, cy), color, 2)
                cv2.line(canvas, (cx, cy-20), (cx, cy+20), color, 2)
                label = f"MATCH: {t_info['name']} ({val:.1%})"
            else:
                label = f"FAIL: {t_info['name']} ({val:.1%})"
            
            cv2.putText(canvas, label, (x1, y1 - 10 - t_idx*25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
        out_path = os.path.join(output_dir, f"final_{s_name}")
        cv2.imwrite(out_path, canvas)
        print(f"  Result: final_{s_name} (Score: {val:.2%})")

if __name__ == "__main__":
    SCREENSHOT_DIR = "D:/Project/wvd/test/screenshot"
    TEMPLATE_DIR = "D:/Project/wvd/test/temple"
    RESULT_DIR = "D:/Project/wvd/test/resulty"
    ROI = [95, 971, 799, 1136]
    process_final_matching(SCREENSHOT_DIR, TEMPLATE_DIR, RESULT_DIR, ROI)
