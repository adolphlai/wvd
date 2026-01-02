from pathlib import Path
import cv2
import numpy as np

# Batch test AUTO template matching under different backgrounds.
# Usage: place samples in this folder and run: python auto_match_test.py

HERE = Path(__file__).resolve().parent
# Use template from the same folder as samples.
TEMPLATE = HERE / "AUTO.png"

samples = sorted([p for p in HERE.glob('*.png') if p.name.lower() != 'auto.png'])
if not TEMPLATE.exists():
    raise SystemExit(f'Template not found: {TEMPLATE}')
if not samples:
    raise SystemExit(f'No .png samples found in {HERE}')

tpl = cv2.imread(str(TEMPLATE))
if tpl is None:
    raise SystemExit('Failed to load AUTO template')

def match_score(img, tpl, label):
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    return max_val, max_loc

# Precompute template variants
_tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
_tpl_clahe = _clahe.apply(_tpl_gray)
_tpl_canny = cv2.Canny(_tpl_gray, 50, 150)
_tpl_clahe_canny = cv2.Canny(_tpl_clahe, 50, 150)

methods = [
    ('raw', lambda img: img, tpl),
    ('gray', lambda img: cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), _tpl_gray),
    ('gray+clahe', lambda img: _clahe.apply(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)), _tpl_clahe),
    ('canny', lambda img: cv2.Canny(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 50, 150), _tpl_canny),
    ('clahe+canny', lambda img: cv2.Canny(_clahe.apply(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)), 50, 150), _tpl_clahe_canny),
]

print(f'Template: {TEMPLATE}')
print(f'Samples: {len(samples)}')
print('---')

for sample in samples:
    img = cv2.imread(str(sample))
    if img is None:
        print(f'{sample.name}: failed to load')
        continue
    print(f'== {sample.name} ==')
    scores = []
    for name, transform, t in methods:
        transformed = transform(img)
        score, loc = match_score(transformed, t, name)
        scores.append((name, score, loc))
    for name, score, loc in sorted(scores, key=lambda x: x[1], reverse=True):
        print(f'  {name:12s} score={score:.4f} loc={loc}')
    print('')
