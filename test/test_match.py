import cv2
import numpy as np

def test_matching(template_path, screenshot_path):
    print(f"Testing matching: {template_path} in {screenshot_path}")
    
    # Load images
    template = cv2.imread(template_path)
    screenshot = cv2.imread(screenshot_path)
    
    if template is None or screenshot is None:
        print("Error: Could not load images.")
        return

    # Method 1: Original (BGR)
    res_bgr = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
    _, max_val_bgr, _, max_loc_bgr = cv2.minMaxLoc(res_bgr)
    print(f"BGR Match: {max_val_bgr:.2%}")

    # Method 2: Grayscale
    gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    gray_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
    res_gray = cv2.matchTemplate(gray_screenshot, gray_template, cv2.TM_CCOEFF_NORMED)
    _, max_val_gray, _, max_loc_gray = cv2.minMaxLoc(res_gray)
    print(f"Gray Match: {max_val_gray:.2%}")

    # Method 3: Canny Edges
    edges_template = cv2.Canny(gray_template, 50, 150)
    edges_screenshot = cv2.Canny(gray_screenshot, 50, 150)
    
    # Save edges for visualization (optional)
    cv2.imwrite("d:/Project/wvd/test/edges_template.png", edges_template)
    cv2.imwrite("d:/Project/wvd/test/edges_screenshot.png", edges_screenshot)
    
    res_edges = cv2.matchTemplate(edges_screenshot, edges_template, cv2.TM_CCOEFF_NORMED)
    _, max_val_edges, _, max_loc_edges = cv2.minMaxLoc(res_edges)
    print(f"Edges Match: {max_val_edges:.2%}")

    # Method 4: Grayscale + Masked Match
    # Simple thresholding on template to get a mask (extract text part)
    _, mask = cv2.threshold(gray_template, 150, 255, cv2.THRESH_BINARY)
    cv2.imwrite("d:/Project/wvd/test/mask.png", mask)
    
    # matchTemplate with mask
    # TM_CCORR_NORMED is one of the methods that supports masking
    res_mask = cv2.matchTemplate(screenshot, template, cv2.TM_CCORR_NORMED, mask=mask)
    _, max_val_mask, _, max_loc_mask = cv2.minMaxLoc(res_mask)
    print(f"Masked Match (CCORR_NORMED): {max_val_mask:.2%}")

if __name__ == "__main__":
    test_matching("d:/Project/wvd/test/template.png", "d:/Project/wvd/test/screenshot.png")
