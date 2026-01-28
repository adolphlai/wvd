# 整合 Harken 避讓移動邏輯至主程式

## 目標
將 `test/test_movement_wall.py` 的移動安全判斷邏輯整合到主程式，替代原本重啟後的簡單左右移動。

## 背景
- 原本重啟後的防轉圈邏輯（`src/script.py:6271-6291`）只是簡單的左右點擊
- 新邏輯需要判斷 harken 位置，避免往 harken 方向移動

## 核心邏輯
移動方向是**相對於角色面向**的：
1. 偵測 harken 的**絕對方位**（小地圖座標系）
2. 偵測**角色面向**（方向圖標）
3. 將絕對方位**轉換成相對方位**（哪個按鍵會碰到 harken）
4. 阻止該方向的移動

## 修改內容

### 1. 複製圖片到 images/minimap/
從 `test/temple/` 複製以下檔案到 `images/minimap/`：
- `minimap-bharken.png` - Harken 圖標（大）
- `minimap-mharken.png` - Harken 圖標（中）
- `minimap-sharken.png` - Harken 圖標（小）
- `minimap-up.png` - 方向圖標（上）
- `minimap-down.png` - 方向圖標（下）
- `minimap-left.png` - 方向圖標（左）
- `minimap-right.png` - 方向圖標（右）

### 2. 在 src/utils.py 新增函數

```python
# ===== Minimap 移動安全判斷 =====

def load_minimap_templates():
    """載入小地圖模板（harken 和方向圖標）"""
    # 返回 (avoid_templates, direction_templates)

def detect_character_direction(minimap_img, direction_templates):
    """偵測角色當前朝向（方向圖標）"""
    # 返回: "上" / "下" / "左" / "右" / None

def get_harken_absolute_direction(minimap_img, avoid_templates):
    """偵測 harken 相對於小地圖中心的絕對方位"""
    # 返回: "上" / "下" / "左" / "右" / None

def absolute_to_relative_direction(absolute_dir, facing):
    """將絕對方位轉換成相對於角色面向的方位"""
    transform = {
        "上": {"上": "上", "下": "下", "左": "左", "右": "右"},
        "下": {"上": "下", "下": "上", "左": "右", "右": "左"},
        "左": {"上": "右", "下": "左", "左": "上", "右": "下"},
        "右": {"上": "左", "下": "右", "左": "下", "右": "上"},
    }
    return transform.get(facing, {}).get(absolute_dir)

def is_safe_to_move(minimap_img, direction, avoid_templates, direction_templates):
    """
    檢查移動方向是否安全（避免進入 harken）
    返回: (is_safe: bool, danger_direction: str or None)
    """

def compare_minimap_images(img1, img2):
    """比較兩張小地圖的相似度（SSIM）"""
    # 返回: 相似度 0.0-1.0

def probe_move_with_wall_detection(device, direction, minimap_roi, avoid_templates, direction_templates):
    """
    執行單方向移動探測，帶牆壁偵測
    返回: "W" (可走) / "BLOCKED" (撞牆) / "UNSAFE" (有 harken)
    """
```

### 3. 修改 src/script.py

#### 3.1 初始化時載入模板
在適當位置（如 `runtimeContext` 初始化後）載入模板：
```python
_MINIMAP_AVOID_TEMPLATES, _MINIMAP_DIRECTION_TEMPLATES = load_minimap_templates()
```

#### 3.2 修改重啟後防轉圈邏輯
位置：`StateDungeon` 中的 `DungeonState.Dungeon` 分支（約 6271-6291 行）

原邏輯：
```python
if not runtimeContext._STEPAFTERRESTART:
    Press([27,950])   # 左
    Sleep(1)
    Press([853,950])  # 右
    Sleep(1)
    runtimeContext._STEPAFTERRESTART = True
```

新邏輯：
```python
if not runtimeContext._STEPAFTERRESTART:
    minimap_roi = get_minimap_roi(ScreenShot())  # 需要新增 ROI 函數

    # 判斷安全方向並移動
    for direction in ["左", "右"]:
        is_safe, danger_dir = is_safe_to_move(
            minimap_roi, direction,
            _MINIMAP_AVOID_TEMPLATES, _MINIMAP_DIRECTION_TEMPLATES
        )
        if is_safe:
            if direction == "左":
                Press([27, 950])
            else:
                Press([853, 950])
            Sleep(1)

    runtimeContext._STEPAFTERRESTART = True
```

## 關鍵檔案
- `images/minimap/` - 新目錄，存放小地圖模板
- `src/utils.py` - 新增移動安全判斷函數
- `src/script.py` - 修改重啟後防轉圈邏輯

## 常數定義
```python
MINIMAP_ROI = [722, 92, 802, 180]  # 小地圖 ROI
MINIMAP_SIMILARITY_THRESHOLD = 0.8  # 相似度閾值，> 0.8 判定為撞牆
```

## 驗證方式
1. 執行主程式，讓遊戲進入需要重啟的狀態
2. 觀察重啟後的移動行為
3. 確認當 harken 在某方向時，不會往該方向移動
