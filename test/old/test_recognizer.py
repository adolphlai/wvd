from monster_recognizer import MonsterRecognizer
import cv2
import os

def test_recognizer(img_path, template_path):
    recognizer = MonsterRecognizer(template_path=template_path)
    monsters = recognizer.detect(img_path)
    
    print(f"Detected {len(monsters)} monsters")
    img = cv2.imread(img_path)
    
    for i, m in enumerate(monsters):
        print(f"Monster {i}: ID={m.id_num}, Rect={m.rect}, Marker={m.marker_pos}, Species={m.species}")
        x, y, w, h = m.rect
        cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.circle(img, m.marker_pos, 5, (0, 0, 255), -1)

    output_path = "D:/Project/wvd/test/recognizer_result.png"
    cv2.imwrite(output_path, img)
    print(f"Saved result to {output_path}")

if __name__ == "__main__":
    test_recognizer("D:/Project/wvd/test/1.png", "D:/Project/wvd/resources/images/next.png")
