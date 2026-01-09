import os
import cv2
import numpy as np
import batch_status_analyzer as analyzer

def save_image(path, img):
    try:
        # Save image handling unicode paths
        ext = os.path.splitext(path)[1]
        result, n = cv2.imencode(ext, img)
        if result:
            with open(path, mode='wb') as f:
                n.tofile(f)
            return True
    except Exception as e:
        print(f"Error saving {path}: {e}")
    return False

def main():
    base_dir = r"D:\Project\wvd\detect"
    debug_dir = os.path.join(base_dir, "debug_screens")
    result_dir = os.path.join(debug_dir, "result")
    
    if not os.path.exists(result_dir):
        os.makedirs(result_dir)
        print(f"Created result directory: {result_dir}")

    # Load all templates
    templates = {}
    print("Loading templates...")
    for folder, template_name, label in analyzer.FOLDERS:
        template_path = os.path.join(base_dir, folder, template_name)
        tmpl = analyzer.load_image(template_path)
        if tmpl is not None:
            templates[label] = tmpl
        else:
            print(f"  Warning: Could not load template for {label}")

    if not os.path.exists(debug_dir):
        print(f"Error: Directory {debug_dir} does not exist.")
        return

    # Filter for image files
    debug_images = [f for f in os.listdir(debug_dir) 
                   if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))]
    debug_images.sort()

    print(f"\n[Processing {len(debug_images)} images...]")
    
    count_processed = 0
    count_detected = 0

    for img_name in debug_images:
        img_path = os.path.join(debug_dir, img_name)
        screen = analyzer.load_image(img_path)
        if screen is None: 
            print(f"Failed to load: {img_name}")
            continue

        detections = []
        is_modified = False
        
        # Keep a clean copy for analysis, draw on 'screen'
        clean_screen = screen.copy()
        
        # Check against all status types
        for label, template in templates.items():
            check_func = analyzer.CHECK_FUNCTIONS.get(label)
            if not check_func: continue
            
            # Check all ROIs
            for i, (x, y, w, h) in enumerate(analyzer.ROIS):
                 # Boundary check
                 if y + h > clean_screen.shape[0] or x + w > clean_screen.shape[1]: continue
                 
                 crop = clean_screen[y:y+h, x:x+w]
                 
                 is_detected, match_val = check_func(crop, template)
                 match_pct = match_val * 100
                 
                 if is_detected:
                     # Calculate position for drawing
                     # We need the max_loc within the crop to draw the rect around the matched icon accurately
                     # But simple ROI labeling is also fine. Let's try to match prompt behavior in batch_status_analyzer.py
                     res = cv2.matchTemplate(crop, template, cv2.TM_CCOEFF_NORMED)
                     _, _, _, max_loc = cv2.minMaxLoc(res)
                     
                     top_left = (x + max_loc[0], y + max_loc[1])
                     bottom_right = (top_left[0] + template.shape[1], top_left[1] + template.shape[0])
                     
                     # Draw Rectangle
                     cv2.rectangle(screen, top_left, bottom_right, (0, 0, 255), 3) # Red box
                     
                     # Draw Text
                     text = f"{label} {match_pct:.0f}%"
                     # Background for text for better readability
                     (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                     cv2.rectangle(screen, (top_left[0], top_left[1] - 25), (top_left[0] + tw, top_left[1]), (0, 0, 255), -1)
                     cv2.putText(screen, text, (top_left[0], top_left[1] - 5), 
                                 cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                     
                     detections.append(f"{label}({match_pct:.0f}%)")
                     is_modified = True

        # Save result even if nothing detected, or maybe only if detected?
        # User said "將結果在圖片上框起來", implies copying all images but annotating those with issues.
        # But usually in batch processing one wants to see all checks.
        # Let's save all to result folder so they can see what was checked.
        
        save_path = os.path.join(result_dir, img_name)
        save_image(save_path, screen)
        
        log_msg = f"Saved: {img_name}"
        if detections:
            log_msg += f" | Detected: {', '.join(detections)}"
            count_detected += 1
        try:
            print(log_msg)
        except UnicodeEncodeError:
            print(log_msg.encode('ascii', errors='replace').decode('ascii'))
        count_processed += 1

    print("-" * 50)
    print(f"Done. Processed: {count_processed}, Images with items found: {count_detected}")
    print(f"Results saved to: {result_dir}")

if __name__ == "__main__":
    main()
