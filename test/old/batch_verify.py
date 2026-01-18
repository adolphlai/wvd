import cv2
import numpy as np
import os

def process_matching(screenshot_dir, template_dir, output_dir, roi):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    screenshots = [f for f in os.listdir(screenshot_dir) if f.endswith('.png') and 'result' not in f and 'res_' not in f and 'match_' not in f]
    print(f"Found {len(screenshots)} screenshots in {screenshot_dir}")
    # Get all templates
    templates = [f for f in os.listdir(template_dir) if f.endswith('.png')]
    
    # Load templates and pre-process them with Laplacian
    tpl_data = []
    for t_name in templates:
        path = os.path.join(template_dir, t_name)
        img = cv2.imread(path)
        if img is None: continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        lap = cv2.Laplacian(gray, cv2.CV_8U)
        tpl_data.append({
            'name': t_name,
            'orig': img,
            'lap': lap
        })
        
    x1, y1, x2, y2 = roi
    
    print(f"Starting batch matching... Templates: {[t['name'] for t in tpl_data]}")
    
    for s_name in screenshots:
        s_path = os.path.join(screenshot_dir, s_name)
        canvas = cv2.imread(s_path)
        if canvas is None: continue
        
        # Draw ROI for reference
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (255, 100, 0), 2)
        
        search_roi = canvas[y1:y2, x1:x2]
        gray_search = cv2.cvtColor(search_roi, cv2.COLOR_BGR2GRAY)
        lap_search = cv2.Laplacian(gray_search, cv2.CV_8U)
        
        for t_idx, t_info in enumerate(tpl_data):
            # Match using Laplacian
            res = cv2.matchTemplate(lap_search, t_info['lap'], cv2.TM_CCOEFF_NORMED)
            _, val, _, loc = cv2.minMaxLoc(res)
            
            # Center coordinate in original screen
            tw, th = t_info['orig'].shape[1], t_info['orig'].shape[0]
            cx = x1 + loc[0] + tw // 2
            cy = y1 + loc[1] + th // 2
            
            # Colors for different templates
            color = (0, 0, 255) if t_idx == 0 else (0, 255, 0)
            
            # Draw marker
            # Crosshair
            cv2.line(canvas, (cx - 20, cy), (cx + 20, cy), color, 2)
            cv2.line(canvas, (cx, cy - 20), (cx, cy + 20), color, 2)
            # Circle
            cv2.circle(canvas, (cx, cy), 10, color, 1)
            # Label
            label = f"{t_info['name']}: {val:.1%}"
            cv2.putText(canvas, label, (cx + 25, cy + t_idx * 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            
        # Save result
        out_path = os.path.join(output_dir, f"res_{s_name}")
        cv2.imwrite(out_path, canvas)
        print(f"  Processed {s_name} -> {out_path}")

if __name__ == "__main__":
    SCREENSHOT_DIR = "D:/Project/wvd/test/screenshot"
    TEMPLATE_DIR = "D:/Project/wvd/test/temple"
    RESULT_DIR = "D:/Project/wvd/test/resulty"
    ROI = [95, 971, 799, 1136]
    
    process_matching(SCREENSHOT_DIR, TEMPLATE_DIR, RESULT_DIR, ROI)
