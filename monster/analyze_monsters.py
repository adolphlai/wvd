import sys
import os
from pathlib import Path
import cv2
import numpy as np

# Add src to path to allow importing monster_recognizer
current_dir = Path(__file__).parent.absolute()
project_root = current_dir.parent
src_path = project_root / "src"
sys.path.append(str(src_path))

try:
    from monster_recognizer import MonsterRecognizer
except ImportError as e:
    print(f"Error importing modules: {e}")
    print(f"Please ensure {src_path} exists and contains monster_recognizer.py")
    input("Press Enter to exit...")
    sys.exit(1)

def main():
    print("=== Monster Analysis Tool ===")
    
    # Setup directories
    base_dir = current_dir
    original_dir = base_dir / "original"
    result_dir = base_dir / "result"
    
    # Create directories if not exist
    original_dir.mkdir(exist_ok=True)
    result_dir.mkdir(exist_ok=True)
    
    # Species directory
    species_dir = base_dir / "species"
    if not species_dir.exists():
        species_dir.mkdir()
        print(f"Created '{species_dir.name}' folder. Place your bestiary images here.")
    
    # Check template
    template_path = base_dir / "next.png"
    if not template_path.exists():
        print(f"Warning: Template file 'next.png' not found in {base_dir}")
        print("Please place the marker template (inverted triangle) image named 'next.png' in this folder.")
        # Try to find it in previous location just in case
        old_template = base_dir / "detect" / "next.png" # guess
        if old_template.exists():
             print(f"Found template in {old_template}, using that.")
             template_path = old_template
        else:
             print("Cannot proceed without template.")
             input("Press Enter to exit...")
             return

    # Initialize Recognizer
    print("Initializing recognizer...")
    recognizer = MonsterRecognizer(str(template_path), str(species_dir))
    
    # Initialize Tracker
    from monster_recognizer import MonsterTracker
    tracker = MonsterTracker()
    
    # Scan images
    valid_extensions = {".jpg", ".jpeg", ".png", ".bmp"}
    # Sort files to ensure temporal consistency for tracking
    image_files = sorted([f for f in original_dir.iterdir() if f.suffix.lower() in valid_extensions])
    
    if not image_files:
        print(f"No images found in {original_dir}")
        print("Please put your game screenshots in the 'original' folder.")
        input("Press Enter to exit...")
        return
        
    print(f"Found {len(image_files)} images. Starting processing...")
    
    for img_file in image_files:
        print(f"Processing {img_file.name}...")
        try:
            # Detect
            monsters = recognizer.detect(str(img_file))
            
            # Track (Update IDs)
            monsters = tracker.update(monsters)
            
            # Print text result
            print(f"  > Detected {len(monsters)} monsters:")
            for m in monsters:
                status = " [MIST]" if m.has_mist else ""
                x, y, w, h = m.rect
                status = " [MIST]" if m.has_mist else ""
                print(f"    - ID: {m.id_num} | Species: {m.species} | Pos: {m.marker_pos} | ROI: {w}x{h} | Color: {m.dominant_color}{status}")
                        
            # Draw result
            output_file = result_dir / f"result_{img_file.name}"
            recognizer.draw_results(str(img_file), monsters, str(output_file))
            
            # Save Debug ROIs
            debug_roi_dir = base_dir / "debug_rois"
            recognizer.save_debug_rois(str(img_file), monsters, str(debug_roi_dir))
            
            # Pairwise Comparison Analysis
            if len(monsters) >= 2:
                print("  > Structural Similarity Analysis:")
                # Need original image
                img = cv2.imdecode(np.fromfile(str(img_file), dtype=np.uint8), cv2.IMREAD_COLOR)
                for i in range(len(monsters)):
                    for j in range(i + 1, len(monsters)):
                        m1 = monsters[i]
                        m2 = monsters[j]
                        
                        # Get ROIs
                        x1, y1, w1, h1 = m1.rect
                        roi1 = img[y1:y1+h1, x1:x1+w1]
                        
                        x2, y2, w2, h2 = m2.rect
                        roi2 = img[y2:y2+h2, x2:x2+w2]
                        
                        # Compare
                        score, mode = recognizer.match_structure(roi1, roi2)
                        
                        verdict = "Distinct"
                        if score > 0.45: verdict = "Likely SAME"
                        elif score > 0.25: verdict = "Uncertain"
                            
                        print(f"    - #{m1.id_num} vs #{m2.id_num}: Score={score:.3f} ({mode}) -> {verdict}")
            
        except Exception as e:
            print(f"  > Error processing {img_file.name}: {e}")
            import traceback
            traceback.print_exc()

    print("\nAll done! Check 'result' folder for output images.")
    # input("Press Enter to close...") # Optional, maybe annoying if automating

if __name__ == "__main__":
    main()
