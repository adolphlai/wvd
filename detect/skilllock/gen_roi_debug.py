import cv2
import numpy as np
import os

def main():
    img_path = r'D:\Project\wvd\detect\skilllock\skilllock.png'
    output_path = r'D:\Project\wvd\detect\skilllock\roi_debug_v4.png'
    
    # 使用者指定的 ROIS 設定
    ROIS = [
        (137, 1230, 162, 50),  # Character 0
        (420, 1230, 165, 50),  # Character 1
        (704, 1230, 167, 50),  # Character 2
        (137, 1405, 162, 50),  # Character 3
        (420, 1405, 165, 50),  # Character 4
        (704, 1405, 167, 50),  # Character 5
    ]
    
    data = np.fromfile(img_path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    
    if img is None:
        print("Failed to load image")
        return

    for i, (x, y, w, h) in enumerate(ROIS):
        # 畫出紅色外框
        cv2.rectangle(img, (x, y), (x+w, y+h), (0, 0, 255), 2)
        # 寫上編號
        cv2.putText(img, f'ROI {i}', (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
    cv2.imencode('.png', img)[1].tofile(output_path)
    print(f"Debug image saved to {output_path}")

if __name__ == "__main__":
    main()
