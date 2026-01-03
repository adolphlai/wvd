import cv2
import os
import numpy as np

def compare_images():
    # Paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)
    template_path = os.path.join(project_root, 'resources', 'images', 'AUTO.png')
    sample_dir = base_dir

    print(f"Template Path: {template_path}")
    print(f"Sample Directory: {sample_dir}")

    # Load Template
    template = cv2.imdecode(np.fromfile(template_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if template is None:
        print("Error: Could not load template image.")
        return

    # Iterate samples
    for filename in os.listdir(sample_dir):
        if not filename.lower().endswith('.png'):
            continue
        
        # skip if it is the template itself (if user copied it there) but we should probably test it anyway to verify 1.0 match
        
        file_path = os.path.join(sample_dir, filename)
        sample = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        
        if sample is None:
            print(f"Warning: Could not load sample {filename}")
            continue
            
        # Check if sample is smaller than template
        if sample.shape[0] < template.shape[0] or sample.shape[1] < template.shape[1]:
            print(f"[{filename}] Skipped: Sample smaller than template.")
            continue

        # Template Matching
        result = cv2.matchTemplate(sample, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        print(f"[{filename}] Max Confidence: {max_val:.4f} at {max_loc}")

if __name__ == "__main__":
    compare_images()
