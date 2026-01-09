import cv2
import numpy as np
import os

# 角色狀態偵測區域定義 (x, y, w, h)
ROIS = [
    (120, 1210, 250, 80),  # Character 0
    (380, 1210, 250, 80),  # Character 1
    (640, 1210, 250, 80),  # Character 2
    (120, 1390, 250, 80),  # Character 3
    (380, 1390, 250, 80),  # Character 4
    (640, 1390, 250, 80),  # Character 5
]

def load_image(path):
    try:
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return img
    except: return None

def get_hsv_stats(img):
    if img is None: return np.array([0,0,0])
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return np.mean(hsv, axis=(0,1))

# --- 各類異常的專屬檢測邏輯 ---

def check_poison(roi, template):
    res = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val < 0.75: return False, 0
    
    mh, mw = template.shape[:2]
    mx, my = max_loc
    matched_area = roi[my:my+mh, mx:mx+mw]
    hsv = get_hsv_stats(matched_area)
    
    # 中毒 (實測 Hue ~120, Sat > 30) - Adjusted to cover ~108 range found in Pos 2
    color_match = abs(hsv[0] - 118) < 20 and hsv[1] > 30
    return (max_val >= 0.75 and color_match), max_val

def check_venom(roi, template):
    res = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val < 0.75: return False, 0
    
    mh, mw = template.shape[:2]
    mx, my = max_loc
    matched_area = roi[my:my+mh, mx:mx+mw]
    hsv = get_hsv_stats(matched_area)
    
    # 劇毒 (Hue ~130 紫色, Sat > 50)
    color_match = abs(hsv[0] - 130) < 20 and hsv[1] > 50
    return (max_val >= 0.75 and color_match), max_val

def check_stone(roi, template):
    res = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val < 0.75: return False, 0
    
    mh, mw = template.shape[:2]
    mx, my = max_loc
    matched_area = roi[my:my+mh, mx:mx+mw]
    
    top_half = matched_area[:mh//2, :]
    top_hsv = cv2.cvtColor(top_half, cv2.COLOR_BGR2HSV)
    white_mask = cv2.inRange(top_hsv, np.array([0, 0, 180]), np.array([180, 40, 255]))
    white_count = cv2.countNonZero(white_mask)
    
    # 石化 (白色像素 50 < n < 130)
    color_match = (50 < white_count < 130)
    return (max_val >= 0.75 and color_match), max_val

def check_fear(roi, template):
    res = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val < 0.75: return False, 0
    
    # 恐懼使用 absdiff
    mh, mw = template.shape[:2]
    mx, my = max_loc
    matched_area = roi[my:my+mh, mx:mx+mw]
    if matched_area.shape != template.shape: return False, 0
    
    diff_img = cv2.absdiff(matched_area, template)
    diff_val = np.mean(diff_img)
    
    # 寶箱恐懼等變體差異值可能較大 (實測約 33)，放寬門檻
    return (diff_val < 40.0), max_val

def check_skilllock(roi, template):
    res = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    # 技能鎖定目前主要靠高飽和度與形狀
    return (max_val >= 0.75), max_val

def check_paralysis(roi, template):
    res = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    return (max_val >= 0.75), max_val

def check_cursed(roi, template):
    res = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    return (max_val >= 0.75), max_val

# --- 分析流程 ---

CHECK_FUNCTIONS = {
    "Poison": check_poison,
    "Venom": check_venom,
    "Petrified": check_stone,
    "Fear": check_fear,
    "SkillLock": check_skilllock,
    "Paralysis": check_paralysis,
    "Cursed": check_cursed
}

FOLDERS = [
    ("demon_status", "cursed_icon.png", "Cursed"),

    ("麻痺", "paralysis_icon.png", "Paralysis"),
    ("中毒", "Poison_icon.png", "Poison"),
    ("劇毒", "poisonous_icon.png", "Venom"),
    ("stone", "stone_icon.png", "Petrified"),
    ("fear_sample", "fear_icon.png", "Fear"),
    ("skilllock", "skilllock_icon.png", "SkillLock")
]

def analyze_folder(base_dir, folder_name, template_name, label):
    folder_path = os.path.join(base_dir, folder_name)
    template_path = os.path.join(folder_path, template_name)
    
    template = load_image(template_path)
    if template is None: return

    print(f"\n[Analyzing {label} - Folder: {folder_name}]")
    print(f"{'Image':<20} | {'Char':<4} | {'Match %':<8} | {'Status'}")
    print("-" * 55)

    files = [f for f in os.listdir(folder_path) if f.lower().endswith('.png') 
             and not f.startswith('result_') and f != template_name]

    check_func = CHECK_FUNCTIONS.get(label)

    for img_name in files:
        img_path = os.path.join(folder_path, img_name)
        screen = load_image(img_path)
        if screen is None: continue

        for i, (x, y, w, h) in enumerate(ROIS):
            if y + h > screen.shape[0] or x + w > screen.shape[1]: continue
            crop = screen[y:y+h, x:x+w]
            
            is_detected, match_val = check_func(crop, template)
            match_pct = match_val * 100
            
            if is_detected:
                print(f"{img_name:<20} | {i:<4} | {match_pct:>6.2f}% | DETECTED")
                # 視覺化標記
                color = (0, 255, 0)
                res = cv2.matchTemplate(crop, template, cv2.TM_CCOEFF_NORMED)
                _, _, _, max_loc = cv2.minMaxLoc(res)
                top_left = (x + max_loc[0], y + max_loc[1])
                bottom_right = (top_left[0] + template.shape[1], top_left[1] + template.shape[0])
                cv2.rectangle(screen, top_left, bottom_right, color, 2)
                cv2.putText(screen, f"{label}:{match_pct:.0f}%", (x, y-5), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        output_name = f"result_all_{img_name}"
        cv2.imencode('.png', screen)[1].tofile(os.path.join(folder_path, output_name))

def main():
    base_dir = r"D:\Project\wvd\detect"
    for folder, template, label in FOLDERS:
        analyze_folder(base_dir, folder, template, label)

if __name__ == "__main__":
    main()
