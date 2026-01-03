import cv2
import os
import numpy as np

def test_fear_detection():
    """測試 chestfear.png 對其他遊戲截圖的匹配"""
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(script_dir, 'chestfear.png')
    
    # 載入模板
    template = cv2.imdecode(np.fromfile(template_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if template is None:
        print(f"❌ 無法載入模板: {template_path}")
        return
    
    print(f"模板: chestfear.png")
    print(f"模板尺寸: {template.shape}")
    print("-" * 50)
    
    # 遍歷資料夾中的其他圖片
    for filename in os.listdir(script_dir):
        if filename == 'chestfear.png' or not filename.endswith('.png'):
            continue
        if filename.endswith('.py'):
            continue
            
        img_path = os.path.join(script_dir, filename)
        img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        
        if img is None:
            print(f"[{filename}] ❌ 無法載入")
            continue
        
        # 確保模板不大於圖片
        if template.shape[0] > img.shape[0] or template.shape[1] > img.shape[1]:
            print(f"[{filename}] ⚠️ 模板大於圖片，跳過")
            continue
        
        # 模板匹配
        result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        
        # 判定結果
        status = "✓ 找到" if max_val >= 0.80 else "✗ 未找到"
        print(f"[{filename}] {status} - 匹配度: {max_val*100:.2f}% 位置: {max_loc}")

if __name__ == "__main__":
    test_fear_detection()
