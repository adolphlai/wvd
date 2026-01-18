import cv2
import numpy as np
import os

def verify_skill_target(screenshot_path, template_path, output_path):
    print(f"Loading screenshot: {screenshot_path}")
    scn = cv2.imread(screenshot_path)
    if scn is None:
        print("Error: Could not load screenshot")
        return

    print(f"Loading template: {template_path}")
    temp = cv2.imread(template_path)
    if temp is None:
        print("Error: Could not load template")
        return

    # Match NEXT
    res = cv2.matchTemplate(scn, temp, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    
    if max_val < 0.7:
        print(f"Error: NEXT not found (Match: {max_val:.2%})")
        return

    # Center of NEXT
    next_pos = [max_loc[0] + temp.shape[1]//2, max_loc[1] + temp.shape[0]//2]
    print(f"Found NEXT at: {max_loc}, Center: {next_pos}, Match: {max_val:.2%}")

    # Clicking logic from script.py
    # target_x1 = next_pos[0] - 15
    # target_x2 = next_pos[0]
    # target_y1 = next_pos[1] + 100
    # target_y2 = next_pos[1] + 170
    # target_y3 = next_pos[1] + 260
    
    targets = [
        (next_pos[0] - 15, next_pos[1] + 100),
        (next_pos[0] - 15, next_pos[1] + 170),
        (next_pos[0] - 15, next_pos[1] + 260),
        (next_pos[0], next_pos[1] + 100),
        (next_pos[0], next_pos[1] + 170),
        (next_pos[0], next_pos[1] + 260),
    ]

    # Draw everything on a copy
    out_img = scn.copy()
    
    # Draw NEXT bounding box
    cv2.rectangle(out_img, max_loc, (max_loc[0] + temp.shape[1], max_loc[1] + temp.shape[0]), (0, 255, 0), 2)
    
    # Draw click targets
    for i, (tx, ty) in enumerate(targets):
        print(f"Target {i+1}: ({tx}, {ty})")
        cv2.circle(out_img, (int(tx), int(ty)), 10, (0, 0, 255), -1)
        cv2.putText(out_img, f"Click {i+1}", (int(tx)+15, int(ty)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

    cv2.imwrite(output_path, out_img)
    print(f"Result saved to: {output_path}")

if __name__ == "__main__":
    verify_skill_target("D:/Project/wvd/test/1.png", "D:/Project/wvd/resources/images/next.png", "D:/Project/wvd/test/result_1.png")
