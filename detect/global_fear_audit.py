import cv2
import numpy as np
import os

# Configuration
BASE_DIR = r"D:\Project\wvd\detect"
TEMPLATE_PATH = r"D:\Project\wvd\resources\images\detect\fear_icon.png"

# ROIs used in the main script
ROIS = [
    (120, 1210, 250, 80), (380, 1210, 250, 80), (640, 1210, 250, 80),
    (120, 1390, 250, 80), (380, 1390, 250, 80), (640, 1390, 250, 80),
]

# Folders to scan
SCAN_FOLDERS = [
    "fear_sample", # Target
    "demon_status", # Cursed
    "麻痺",          # Paralysis
    "中毒",          # Poison
    "劇毒",          # Venom
    "stone"         # Stone
]

def load_image(path):
    try:
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return img
    except:
        return None

def check_fear(img, template):
    results = []
    
    for idx, (x, y, w, h) in enumerate(ROIS):
        if y+h > img.shape[0] or x+w > img.shape[1]: continue
        
        roi = img[y:y+h, x:x+w]
        
        # 1. Template Match
        res = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        
        if max_val >= 0.75:
            # 2. Extract Matched Area
            top_left = max_loc
            h_t, w_t = template.shape[:2]
            matched_area = roi[top_left[1]:top_left[1]+h_t, top_left[0]:top_left[0]+w_t]
            
            # 3. ABS Diff Check
            # Ensure shape matches (it should, but clip if needed)
            if matched_area.shape != template.shape:
                continue
                
            diff_img = cv2.absdiff(matched_area, template)
            diff_val = np.mean(diff_img)
            
            # 4. HSV Check (Keep for Ref)
            hsv = cv2.cvtColor(matched_area, cv2.COLOR_BGR2HSV)
            avg_hue = np.mean(hsv[:,:,0])
            avg_sat = np.mean(hsv[:,:,1])
            
            # Combined Logic: Diff < 7.0 (Strict shape+color match)
            is_fear = (diff_val < 7.0)
            
            results.append({
                "char_idx": idx,
                "match_val": max_val,
                "diff": diff_val,
                "hue": avg_hue,
                "sat": avg_sat,
                "is_fear": is_fear
            })
            
    return results

def main():
    print(f"Loading template from: {TEMPLATE_PATH}")
    template = load_image(TEMPLATE_PATH)
    if template is None:
        template = load_image(os.path.join(BASE_DIR, "fear_sample", "fear_icon.png"))
        if template is None:
            print("Failed to load template.")
            return

    print("\n" + "="*100)
    print(f"{'狀態':<10} | {'圖片':<15} | {'匹配%':<8} | {'Diff':<8} | {'Hue':<6} | {'Sat':<6} | {'結果'}")
    print("-" * 100)

    total_images = 0
    total_detected = 0
    false_positives = 0

    for folder in SCAN_FOLDERS:
        folder_path = os.path.join(BASE_DIR, folder)
        if not os.path.exists(folder_path): continue
        
        files = [f for f in os.listdir(folder_path) if f.lower().endswith(".png") and "icon" not in f and "result" not in f]
        total_images += len(files)
        
        for f in files:
            img_path = os.path.join(folder_path, f)
            img = load_image(img_path)
            if img is None: continue
            
            detections = check_fear(img, template)
            
            if not detections:
                continue

            for d in detections:
                is_target_folder = (folder == "fear_sample")
                result_str = ""
                
                if d['is_fear']:
                    if is_target_folder:
                        result_str = "✅ 成功"
                        total_detected += 1
                    else:
                        result_str = "❌ 誤判"
                        false_positives += 1
                else:
                    if is_target_folder:
                         result_str = "⚠️ 漏抓"
                    else:
                         result_str = "🛡️ 過濾"

                if d['match_val'] > 0.6 or is_target_folder:
                    folder_name = "Fear" if folder == "fear_sample" else folder
                    print(f"{folder_name:<10} | {f:<15} | {d['match_val']*100:>6.2f}% | {d['diff']:>8.2f} | {d['hue']:>6.1f} | {d['sat']:>6.1f} | {result_str}")

    print("="*100)
    print(f"總計掃描圖片: {total_images} 張")
    print(f"正確偵測 (恐懼): {total_detected}")
    print(f"誤判數 (False Positives): {false_positives}")
    
    if false_positives == 0 and total_detected > 0:
        print("\n✅ 驗證通過：恐懼偵測邏輯精準，無誤判且能正確識別目標。")
    elif false_positives > 0:
        print("\n❌ 驗證失敗：存在誤判，請調整參數。")
    else:
        print("\n⚠️ 驗證警告：未偵測到任何恐懼狀態（可能是圖片問題）。")

if __name__ == "__main__":
    main()
