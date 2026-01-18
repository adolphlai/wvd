import cv2
import numpy as np
import os

def test_methods(img_path, tpl_path, roi):
    img = cv2.imread(img_path)
    tpl = cv2.imread(tpl_path)
    if img is None or tpl is None: return None
    
    x1, y1, x2, y2 = roi
    search = img[y1:y2, x1:x2]
    
    gray_search = cv2.cvtColor(search, cv2.COLOR_BGR2GRAY)
    gray_tpl = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
    
    results = {}
    
    # Method 1: Standard BGR
    res1 = cv2.matchTemplate(search, tpl, cv2.TM_CCOEFF_NORMED)
    _, v1, _, l1 = cv2.minMaxLoc(res1)
    results['BGR'] = (v1, (x1 + l1[0] + tpl.shape[1]//2, y1 + l1[1] + tpl.shape[0]//2))
    
    # Method 2: Canny Edge
    edges_search = cv2.Canny(gray_search, 50, 150)
    edges_tpl = cv2.Canny(gray_tpl, 50, 150)
    res2 = cv2.matchTemplate(edges_search, edges_tpl, cv2.TM_CCOEFF_NORMED)
    _, v2, _, l2 = cv2.minMaxLoc(res2)
    results['Canny'] = (v2, (x1 + l2[0] + tpl.shape[1]//2, y1 + l2[1] + tpl.shape[0]//2))
    
    # Method 3: Laplacian (Focus on fine details, good for text)
    lap_search = cv2.Laplacian(gray_search, cv2.CV_8U)
    lap_tpl = cv2.Laplacian(gray_tpl, cv2.CV_8U)
    res3 = cv2.matchTemplate(lap_search, lap_tpl, cv2.TM_CCOEFF_NORMED)
    _, v3, _, l3 = cv2.minMaxLoc(res3)
    results['Laplacian'] = (v3, (x1 + l3[0] + tpl.shape[1]//2, y1 + l3[1] + tpl.shape[0]//2))

    # Method 4: Grayscale CCOEFF (Baseline for "no color")
    res4 = cv2.matchTemplate(gray_search, gray_tpl, cv2.TM_CCOEFF_NORMED)
    _, v4, _, l4 = cv2.minMaxLoc(res4)
    results['Gray'] = (v4, (x1 + l4[0] + tpl.shape[1]//2, y1 + l4[1] + tpl.shape[0]//2))

    return results

if __name__ == "__main__":
    tpl_path = 'D:/Project/wvd/test/template.png'
    roi = [95, 971, 799, 1136]
    files = ['1.png', '2.png', '3.png', '4.png', 'wind1.png', 'wind2.png', 'wind3.png', 'fire1.png', 'fire2.png', 'fire3.png', 'fire4.png']
    
    print('| 圖片 | BGR | Canny | Laplacian | Gray | 實際狀態 |')
    print('|---|---|---|---|---|---|')
    
    for f in files:
        path = f'D:/Project/wvd/test/{f}'
        r = test_methods(path, tpl_path, roi)
        if not r: continue
        
        status = "不存在"
        if f == '1.png': status = "TL"
        elif f == '2.png': status = "TR"
        elif f == 'wind1.png': status = "BL"
        elif f == 'wind2.png': status = "BR"
        elif f == 'wind3.png': status = "TR"
        
        def fmt(name):
            val, pos = r[name]
            return f"{val:.1%}/{pos}"

        print(f"| {f} | {fmt('BGR')} | {fmt('Canny')} | {fmt('Laplacian')} | {fmt('Gray')} | {status} |")
