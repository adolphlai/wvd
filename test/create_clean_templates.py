import cv2
import numpy as np
import os

def smart_clean(path, output_path, threshold=50):
    img = cv2.imread(path)
    if img is None: return
    
    # 轉為灰階分析亮度
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 1. 亮度門檻：文字是白色的 (亮度高)，背景通常亮度低
    lumi_mask = np.where(gray > 90, 255, 0).astype(np.uint8)
    
    # 2. 多點背景色排除：偵測四個角落的背景色
    corners = [img[0,0], img[0, -1], img[-1, 0], img[-1, -1]]
    color_masks = []
    for bg_color in corners:
        diff = np.sqrt(np.sum((img.astype(float) - bg_color.astype(float))**2, axis=2))
        color_masks.append(np.where(diff < threshold, 0, 255).astype(np.uint8))
    
    # 合併遮罩：必須同時滿足「非背景色」且「具有一定亮度」才保留
    final_mask = lumi_mask
    for c_mask in color_masks:
        final_mask = cv2.bitwise_and(final_mask, c_mask)
        
    # 平滑處理
    final_mask = cv2.GaussianBlur(final_mask, (3,3), 0)
    
    bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = final_mask
    cv2.imwrite(output_path, bgra)
    print(f"Deep cleaned: {output_path}")

if __name__ == "__main__":
    template_dir = "D:/Project/wvd/test/temple"
    # 自動掃描所有原始圖片並執行去背
    files = [f for f in os.listdir(template_dir) if f.endswith('.png') and not f.endswith('_clean.png')]
    
    print(f"Start cleaning {len(files)} templates...")
    for f in files:
        input_path = os.path.join(template_dir, f)
        output_path = os.path.join(template_dir, f.replace(".png", "_clean.png"))
        smart_clean(input_path, output_path)
    print("All tasks completed.")
