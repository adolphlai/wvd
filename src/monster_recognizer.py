import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import os

class MonsterInfo:
    """單隻怪物的辨識資訊"""
    def __init__(self, id_num: int, rect: Tuple[int, int, int, int], 
                 marker_pos: Tuple[int, int], depth: float):
        self.id_num = id_num
        self.rect = rect # (x, y, w, h)
        self.marker_pos = marker_pos # (mx, my) 下一關標記的中心點
        self.depth = depth # y 軸座標，越大越靠近前景
        self.species = "Unknown"
        self.has_mist = False # 是否有紫霧/特效
        self.dominant_color = "Unknown" # 主色調
        self.histogram = None # 特徵直方圖
        self.is_selected = False # 是否被選中 (NEXT 標記)

class MonsterRecognizer:
    """
    怪物辨識核心模組
    
    功能:
    1. 定位: 使用 inverted triangle (Next marker) 定位怪物頭頂
    2. 範圍: 根據 marker 推算身體 ROI
    3. 特效: 檢測紫霧 (Purple Mist)
    4. 排序: 處理 3D 遮擋，依 Y 軸排序 (Painter's Algorithm)
    """
    def __init__(self, template_path: str = None, species_lib_path: str = None):
        self.template = None
        if template_path and os.path.exists(template_path):
            self.load_template(template_path)
            
        self.species_lib = None
        if species_lib_path and os.path.exists(species_lib_path):
            self.species_lib = SpeciesLibrary(species_lib_path)
        
        # 色彩設定 (HSV)
        # 紫霧範圍 (根據經驗值，可調整)
        self.MIST_LOWER = np.array([125, 30, 30])
        self.MIST_UPPER = np.array([165, 255, 255])
        
        # ORB for Dynamic ROI
        self.orb = cv2.ORB_create(nfeatures=500, fastThreshold=0)

    def load_template(self, path: str):
        """載入標記模板 (Next Icon)"""
        # 讀取為彩色以保留特徵，但比對時可轉灰階
        self.template = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        self.tpl_h, self.tpl_w = self.template.shape[:2]

    def detect(self, image_path: str) -> List[MonsterInfo]:
        """
        對單張圖片進行怪物偵測
        Args:
            image_path: 圖片路徑
        Returns:
            List[MonsterInfo]: 偵測到的怪物列表，已按前後順序排序(前->後 or 後->前)
        """
        img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            print(f"Error: 無法讀取圖片 {image_path}")
            return []

        # 1. 尋找標記 (Markers)
        markers = self._find_markers(img)
        
        # 2. 生成怪物資訊並分析
        monsters = []
        for i, (mx, my, mw, mh) in enumerate(markers):
            # 用戶回饋: 每個怪不同大小
            # 調整: 使用特徵點動態估算範圍
            bx, by, bw, bh = self._estimate_body_roi(img, mx, my + mh//2)
            
            m_info = MonsterInfo(i, (bx, by, bw, bh), (mx, my), depth=by + bh)
            
            # 3. 特效與顏色分析
            body_roi = img[by:by+bh, bx:bx+bw]
            m_info.has_mist = self._check_mist_effect(body_roi)
            m_info.dominant_color = self._get_dominant_color_name(body_roi)
            m_info.histogram = self._compute_roi_histogram(body_roi) # 計算特徵直方圖供追蹤使用
            
            # 4. 物種辨識 (Species Identification)
            # 使用新版 identify (Feature + Color)
            if self.species_lib:
                m_info.species, confidence = self.species_lib.identify(body_roi)
                # 信心度太低則標記為 Unknown
                if confidence < 0.5: 
                     m_info.species = f"Unknown ({confidence:.2f})"
                else:
                     m_info.species = f"{m_info.species} ({confidence:.2f})"
            
            monsters.append(m_info)

        # 5. 排序: 根據 depth (Y 座標較大者在前景)
        monsters.sort(key=lambda m: m.depth, reverse=True)
        
        # 重新編號
        for idx, m in enumerate(monsters):
            m.id_num = idx

        return monsters

    def compare_monsters(self, m1: MonsterInfo, m2: MonsterInfo) -> float:
        """比較兩隻怪物的相似度 (0~1, 越低越像)"""
        if m1.histogram is None or m2.histogram is None:
            return 1.0
        return cv2.compareHist(m1.histogram, m2.histogram, cv2.HISTCMP_BHATTACHARYYA)
        
    def _compute_roi_histogram(self, roi):
        """計算 ROI 的特徵直方圖 (含中心遮罩)"""
        if roi is None or roi.size == 0:
            return None
        h, w = roi.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.ellipse(mask, (w//2, h//2), (int(w*0.4), int(h*0.4)), 0, 0, 360, 255, -1)
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], mask, [12, 8], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        return hist
    
    def _get_dominant_color_name(self, roi) -> str:
        """簡易分析區域主色調 (Hue)"""
        if roi is None or roi.size == 0:
            return "None"
            
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        # 計算 Hue 直方圖
        hist = cv2.calcHist([hsv], [0], None, [180], [0, 180])
        dominant_hue = np.argmax(hist)
        
        # 簡單映射 Hue 到顏色名稱
        if dominant_hue < 10 or dominant_hue > 170: return "Red"
        if 10 <= dominant_hue < 25: return "Orange"
        if 25 <= dominant_hue < 35: return "Yellow"
        if 35 <= dominant_hue < 85: return "Green"
        if 85 <= dominant_hue < 125: return "Blue"
        if 125 <= dominant_hue < 145: return "Purple"
        if 145 <= dominant_hue < 170: return "Pink"
        return "Unknown"

    def _find_markers(self, img) -> List[Tuple[int, int, int, int]]:
        """
        使用多尺度模板匹配尋找標記
        Returns list of (center_x, center_y, w, h)
        """
        if self.template is None:
            return []

        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.cvtColor(self.template, cv2.COLOR_BGR2GRAY)
        th, tw = tpl_gray.shape[:2]

        found_markers = []
        
        # 限制搜尋區域 (通常怪物標記不會在最底部 UI 區，也不會太靠邊)
        # 優化效能用，目前先搜全圖或中間區域
        
        # 多尺度
        for scale in np.linspace(0.6, 1.4, 5): # 0.6x to 1.4x size
            resized_tw = int(tw * scale)
            resized_th = int(th * scale)
            if resized_tw > img_gray.shape[1] or resized_th > img_gray.shape[0]:
                continue

            resized_tpl = cv2.resize(tpl_gray, (resized_tw, resized_th))
            
            res = cv2.matchTemplate(img_gray, resized_tpl, cv2.TM_CCOEFF_NORMED)
            threshold = 0.8 # 匹配門檻
            
            loc = np.where(res >= threshold)
            for pt in zip(*loc[::-1]): # (x, y) top-left
                center_x = pt[0] + resized_tw // 2
                center_y = pt[1] + resized_th // 2
                
                # 檢查是否與已存在的標記重疊 (Non-Maximum Suppression 簡化版)
                is_duplicate = False
                for exist_m in found_markers:
                    ex, ey, _, _ = exist_m
                    dist = ((center_x - ex)**2 + (center_y - ey)**2)**0.5
                    if dist < 20: # 距離太近視為同一個
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    found_markers.append((center_x, center_y, resized_tw, resized_th))

        return found_markers

    def _check_mist_effect(self, roi) -> bool:
        """檢查區域內是否有特定顏色特效 (如紫霧)"""
        if roi is None or roi.size == 0:
            return False
            
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.MIST_LOWER, self.MIST_UPPER)
        
        # 計算白色像素 (符合顏色範圍) 佔比
        count = cv2.countNonZero(mask)
        ratio = count / (roi.shape[0] * roi.shape[1])
        
        # 如果超過 5% 區域是紫色，視為有特效
        return ratio > 0.05

    def _estimate_body_roi(self, img, mx, my) -> Tuple[int, int, int, int]:
        """
        使用特徵點分佈動態估算怪物身體範圍
        Returns: (x, y, w, h) absolute coordinates
        """
        h_img, w_img = img.shape[:2]
        
        # 1. 定義最大搜尋範圍 (Max Search Region)
        # 假設怪物在標記正下方，最大不超過 400x400
        search_w = 400
        search_h = 400
        sx = max(0, mx - search_w // 2)
        sy = my # 從標記位置開始往下
        sw = min(w_img - sx, search_w)
        sh = min(h_img - sy, search_h)
        
        if sw <= 0 or sh <= 0:
            return (mx - 50, my, 100, 150) # Fallback
            
        search_roi = img[sy:sy+sh, sx:sx+sw]
        
        # 2. 檢測特徵點
        gray = cv2.cvtColor(search_roi, cv2.COLOR_BGR2GRAY)
        kp = self.orb.detect(gray, None)
        
        if not kp:
             print(f"  [ROI Debug] No keypoints found at ({mx}, {my}). Using fallback.")
             return (mx - 50, my, 100, 150) # Fallback
             
        # 3. 過濾離群點 & 找出包圍盒 (Bounding Box)
        # 轉換回絕對座標
        points = []
        for k in kp:
            px, py = k.pt
            abs_x = sx + px
            abs_y = sy + py
            
            # 過濾規則:
            # X 軸: 必須在標記左右一定範圍內 (避免框到隔壁怪)
            if abs(abs_x - mx) > 120: continue
            
            # Y 軸: 必須在標記下方
            if abs_y < my: continue
            
            points.append((abs_x, abs_y))
            
        if len(points) < 5:
             print(f"  [ROI Debug] Too few keypoints ({len(points)}). Using fallback.")
             return (mx - 50, my, 100, 150) # Fallback (特徵太少)
             
        points = np.array(points, dtype=np.int32)
        x, y, w, h = cv2.boundingRect(points)
        
        # 稍微擴大一點框 (Padding)
        pad = 10
        x = max(0, x - pad)
        y = max(0, y) # Top usually strict
        w = min(w_img - x, w + pad*2)
        h = min(h_img - y, h + pad)
        
        # 限制最小/最大尺寸
        w = max(50, min(w, 300))
        h = max(80, min(h, 400))
        
        print(f"  [ROI Debug] Dynamic ROI: {w}x{h} (KP: {len(points)})")
        
        return int(x), int(y), int(w), int(h)

    def draw_results(self, img_path: str, monsters: List[MonsterInfo], output_path: str):
        """繪製結果並存檔"""
        img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        
        for m in monsters:
            # 畫框
            x, y, w, h = m.rect
            color = (0, 0, 255) # Red for normal
            
            if m.has_mist:
                color = (255, 0, 255) # Purple for mist
            
            cv2.rectangle(img, (x, y), (x+w, y+h), color, 2)
            
            # 畫標記點
            mx, my = m.marker_pos
            cv2.circle(img, (mx, my), 5, (0, 255, 0), -1)
            
            # 標籤 (A, B, C... or #0, #1...)
            # label_char = chr(ord('A') + m.id_num) 
            # Tracker 使用持續增長的 ID，改為顯示數字比較安全
            label_char = f"#{m.id_num}"
            
            # 顯示資訊: ID + 物種 + (特效)
            tag_text = ""
            if m.has_mist: tag_text += "[MIST]"
            if m.species != "Unknown": tag_text += f" {m.species}"
            
            label = f"{label_char} {tag_text}"
            
            # 文字背景
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(img, (x, y - 20), (x + tw + 10, y + 5), color, -1)
            cv2.putText(img, label, (x + 5, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        cv2.imwrite(output_path, img)
        print(f"結果已保存: {output_path}")

    def save_debug_rois(self, img_path: str, monsters: List[MonsterInfo], output_dir: str):
        """儲存怪物的裁切 ROI 供除錯"""
        img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None: return
        
        Path(output_dir).mkdir(exist_ok=True, parents=True)
        base_name = Path(img_path).stem
        
        for m in monsters:
            x, y, w, h = m.rect
            roi = img[y:y+h, x:x+w]
            if roi.size > 0:
                # 標記是否匹配到物種
                species_tag = m.species if "Unknown" not in m.species else "Unknown"
                fname = f"{base_name}_ID{m.id_num}_{species_tag}.png"
                # Remove invalid chars from filename
                fname = "".join([c for c in fname if c.isalpha() or c.isdigit() or c in '._- '])
                
                cv2.imencode('.png', roi)[1].tofile(str(Path(output_dir) / fname))



    def match_structure(self, roi1, roi2) -> Tuple[float, str]:
        """
        比較兩個 ROI 的結構相似度 (Based on User's RANSAC approach)
        Returns: (Score, Mode) - Score > 0.45 視為相同
        """
        def create_feature():
            if hasattr(cv2, "SIFT_create"):
                return cv2.SIFT_create(nfeatures=1000), cv2.NORM_L2
            return cv2.AKAZE_create(), cv2.NORM_HAMMING

        def preprocess(gray):
            # Stabilize lighting / contrast
            if gray is None: return None
            gray = cv2.GaussianBlur(gray, (3, 3), 0)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            return clahe.apply(gray)

        def get_score(imgA_gray, imgB_gray):
            feat, norm = create_feature()
            
            A = preprocess(imgA_gray)
            B = preprocess(imgB_gray)
            if A is None or B is None: return 0.0

            kA, dA = feat.detectAndCompute(A, None)
            kB, dB = feat.detectAndCompute(B, None)

            if dA is None or dB is None or len(kA) < 5 or len(kB) < 5:
                return 0.0

            matcher = cv2.BFMatcher(norm)
            try:
                knn = matcher.knnMatch(dA, dB, k=2)
            except:
                return 0.0
                
            good = []
            for m, n in knn:
                if m.distance < 0.75 * n.distance:
                    good.append(m)

            if len(good) < 4:
                return 0.0

            ptsA = np.float32([kA[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            ptsB = np.float32([kB[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

            # RANSAC Homography
            try:
                H, mask = cv2.findHomography(ptsA, ptsB, cv2.RANSAC, 5.0)
            except:
                return 0.0
                
            if mask is None:
                return 0.0

            inliers = int(mask.sum())
            ratio = inliers / max(len(good), 1)
            score = ratio * (1.0 + np.log1p(inliers) / 5.0)
            return float(score)

        # Main comparison logic (with Mirror support)
        if roi1 is None or roi2 is None or roi1.size == 0 or roi2.size == 0:
            return 0.0, "none"
            
        g1 = cv2.cvtColor(roi1, cv2.COLOR_BGR2GRAY)
        g2 = cv2.cvtColor(roi2, cv2.COLOR_BGR2GRAY)
        
        # 1. Direct Match
        s1 = get_score(g1, g2)
        
        # 2. Mirror Match (Flip R)
        g2_flip = cv2.flip(g2, 1)
        s2 = get_score(g1, g2_flip)
        
        if s2 > s1:
            return s2, "mirrored"
        return s1, "direct"


class SpeciesLibrary:
    """怪物圖鑑庫，用於比對特徵 (ORB + HSV)"""
    def __init__(self, library_path: str):
        self.library = {} # { name: {'hist': hist, 'des': descriptors} }
        self.path = Path(library_path)
        # ORB 特徵提取器 (共用)
        self.orb = cv2.ORB_create(nfeatures=500)
        # 特徵匹配器
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        
        if self.path.exists():
            self._load_library()
    
    def _load_library(self):
        valid_exts = {'.png', '.jpg', '.jpeg'}
        for img_file in self.path.iterdir():
            if img_file.suffix.lower() in valid_exts:
                # 讀取包含 Alpha Channel (IMREAD_UNCHANGED)
                img = cv2.imdecode(np.fromfile(str(img_file), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                if img is not None:
                    mask = None
                    img_bgr = img
                    if img.shape[2] == 4:
                        b, g, r, a = cv2.split(img)
                        img_bgr = cv2.merge([b, g, r])
                        mask = a

                    # 1. 計算顏色特徵 (HSV Histogram)
                    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
                    hist = cv2.calcHist([hsv], [0, 1], mask, [12, 8], [0, 180, 0, 256])
                    cv2.normalize(hist, hist)
                    
                    # 2. 計算結構特徵 (ORB Keypoints)
                    # ORB 需要灰階圖
                    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
                    kp, des = self.orb.detectAndCompute(gray, mask)
                    
                    self.library[img_file.stem] = {'hist': hist, 'des': des}
                    
        print(f"[SpeciesLib] Loaded {len(self.library)} species from {self.path}")

    def identify(self, roi) -> Tuple[str, float]:
        """
        綜合辨識 (特徵點 + 顏色)
        Returns: (Name, Confidence) - Confidence 0~1 (越高越確信)
        """
        if not self.library or roi is None or roi.size == 0:
            return "Unknown", 0.0
            
        # 準備 ROI 數據
        h, w = roi.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.ellipse(mask, (w//2, h//2), (int(w*0.4), int(h*0.4)), 0, 0, 360, 255, -1)
        
        # 1. ORB 特徵匹配 (結構優先)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        kp, des = self.orb.detectAndCompute(gray, mask)
        
        best_match_name = "Unknown"
        max_matches = 0
        
        if des is not None and len(des) > 0:
            for name, data in self.library.items():
                ref_des = data['des']
                if ref_des is None or len(ref_des) < 2: continue
                
                # KNN 匹配
                try:
                    matches = self.bf.knnMatch(des, ref_des, k=2)
                    # Lowe's Ratio Test
                    good = []
                    for m, n in matches:
                        if m.distance < 0.75 * n.distance:
                            good.append(m)
                    
                    if len(good) > max_matches:
                        max_matches = len(good)
                        best_match_name = name
                except:
                    pass
        
        # 如果特徵點匹配數量夠多 (>4)，直接採信
        if max_matches > 4:
            return best_match_name, min(1.0, max_matches / 20.0) # 20個點算滿分

        # 2. 如果結構特徵不足，退回顏色直方圖 (Histogram)
        # 用於分辨顏色差異大但在遠處模糊的怪
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], mask, [12, 8], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        
        best_hist_name = "Unknown"
        min_dist = 1.0
        
        for name, data in self.library.items():
            dist = cv2.compareHist(hist, data['hist'], cv2.HISTCMP_BHATTACHARYYA)
            if dist < min_dist:
                min_dist = dist
                best_hist_name = name
                
        # 顏色距離 < 0.3 算相似，轉換為信心度 (1 - dist)
        if min_dist < 0.4:
            return best_hist_name, (1.0 - min_dist)
            
        return "Unknown", 0.0

    def match_hist(self, target_hist):
        # Deprecated logic kept for compatibility/fallback if needed, but not used in new flow
        return "Unknown", 1.0


class MonsterTracker:
    """
    跨影格怪物追蹤器
    維持怪物 ID 一致性 (Frame-to-Frame Tracking)
    """
    def __init__(self, max_missing_frames=5):
        self.next_id = 0
        self.tracks = [] # List of {'id': int, 'info': MonsterInfo, 'missing': int}
        self.max_missing = max_missing_frames

    def update(self, detections: List[MonsterInfo]) -> List[MonsterInfo]:
        """
        更新追蹤狀態並返回帶有穩定 ID 的怪物列表
        """
        if not self.tracks:
            # 第一幀，直接分配 ID
            for m in detections:
                m.id_num = self.next_id
                self.tracks.append({'id': self.next_id, 'info': m, 'missing': 0})
                self.next_id += 1
            return detections

        # 簡單匹配: 優先比對位置距離，其次比對直方圖相似度
        # 建立成本矩陣 (Cost Matrix)
        # Cost = Distance * 0.5 + HistDiff * 0.5 (權重可調)
        
        assigned_tracks = set()
        
        # 為每個新偵測到的怪物尋找最佳匹配的軌跡
        for m in detections:
            best_track_idx = -1
            min_cost = 100000.0
            
            mx, my = m.marker_pos
            
            for i, track in enumerate(self.tracks):
                if i in assigned_tracks: continue
                
                t_info = track['info']
                tx, ty = t_info.marker_pos
                
                # 1. 歐式距離 (像素)
                dist = ((mx - tx)**2 + (my - ty)**2)**0.5
                
                # 2. 外觀差異 (直方圖)
                hist_diff = 1.0
                if m.histogram is not None and t_info.histogram is not None:
                    hist_diff = cv2.compareHist(m.histogram, t_info.histogram, cv2.HISTCMP_BHATTACHARYYA)
                
                # 如果距離太遠，視為不同隻 (即使長得像)
                if dist > 300: # 假設幀間移動不超過 300 像素
                     continue
                
                # Cost function
                # 距離權重較大，因為外觀可能因光影、特效變化
                cost = dist + (hist_diff * 200) 
                
                if cost < min_cost:
                    min_cost = cost
                    best_track_idx = i
            
            if best_track_idx != -1:
                # 匹配成功
                track = self.tracks[best_track_idx]
                m.id_num = track['id'] # 繼承 ID
                track['info'] = m # 更新最新狀態
                track['missing'] = 0
                assigned_tracks.add(best_track_idx)
            else:
                # 視為新怪物
                m.id_num = self.next_id
                self.tracks.append({'id': self.next_id, 'info': m, 'missing': 0})
                self.next_id += 1
        
        # 處理未匹配的軌跡 (Missing)
        new_tracks = []
        for i, track in enumerate(self.tracks):
            if i not in assigned_tracks:
                track['missing'] += 1
            if track['missing'] < self.max_missing:
                new_tracks.append(track)
        self.tracks = new_tracks
        
        return detections
