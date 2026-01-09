import cv2
import numpy as np
import os

# 角色狀態偵測區域定義 (x, y, w, h)
ROIS = [
    (120, 1210, 250, 80), (380, 1210, 250, 80), (640, 1210, 250, 80),
    (120, 1390, 250, 80), (380, 1390, 250, 80), (640, 1390, 250, 80),
]

def load_image(path):
    try:
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return img
    except:
        return None

def main():
    base_dir = r"D:\Project\wvd\detect"
    icon_path = os.path.join(base_dir, "skilllock", "skilllock_icon.png")
    icon = load_image(icon_path)
    if icon is None:
        print(f"SkillLock icon not found at {icon_path}!")
        return
    
    mh, mw = icon.shape[:2]

    all_pngs = []
    for root, dirs, files in os.walk(base_dir):
        for f in files:
            name_lower = f.lower()
            if f.lower().endswith(".png") and "icon" not in name_lower and "result" not in name_lower and "mask" not in name_lower and "cropped" not in name_lower:
                all_pngs.append(os.path.join(root, f))

    print(f"Total images to audit for SkillLock: {len(all_pngs)}")
    print(f"{'Folder':<15} | {'Image':<15} | {'Char':<4} | {'Match %':<8} | {'Status'}")
    print("-" * 75)

    positive_count = 0
    for img_path in sorted(all_pngs):
        screen = load_image(img_path)
        if screen is None or screen.shape[0] < 1600: continue
        
        folder = os.path.basename(os.path.dirname(img_path))
        name = os.path.basename(img_path)

        for i, (x, y, w, h) in enumerate(ROIS):
            if y + h > screen.shape[0] or x + w > screen.shape[1]: continue
            
            roi = screen[y:y+h, x:x+w]
            res = cv2.matchTemplate(roi, icon, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            
            match_pct = max_val * 100
            
            # 技能鎖定判定閾值暫定為 75%
            is_skilllock = (match_pct >= 75)
            
            if is_skilllock:
                positive_count += 1
                print(f"{folder:<15} | {name:<15} | {i:<4} | {match_pct:>6.2f}% | DETECTED")
            elif match_pct > 60:
                print(f"{folder:<15} | {name:<15} | {i:<4} | {match_pct:>6.2f}% | (Low Conf)")

    print("-" * 75)
    print(f"Audit Complete. Total SkillLock DETECTED: {positive_count}")

if __name__ == "__main__":
    main()
