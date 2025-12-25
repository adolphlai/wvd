---
description: Resume 按鈕與 routenotfound 檢測邏輯
---

# Resume + routenotfound 檢測邏輯

## 執行環境
- **檔案**: `src/script.py`
- **函數**: `StateDungeon()`
- **狀態**: `DungeonState.Dungeon`

## 處理邏輯流程

```
【DungeonState.Dungeon 狀態】
│
├─ 0. 正在回城中 (_GOHOME_IN_PROGRESS = True)
│     → 繼續執行 gohome（之前被戰鬥/寶箱打斷）
│
├─ 1. 第一次進入地城 (_FIRST_DUNGEON_ENTRY = True)
│     → 無條件打開地圖
│
├─ 2. 剛重啟過遊戲 (_RESTART_OPEN_MAP_PENDING = True)
│     → 跳過 Resume 優化，直接嘗試打開地圖
│
└─ 3. 非第一次進入且非重啟後 (Resume 優化啟用時)
      │
      ├─ 3.0 檢測 Resume 按鈕（最多重試 3 次）
      │       ├─ 檢測到 Resume → 進入 3.1
      │       └─ 3 次都沒檢測到 → 打開地圖
      │
      ├─ 3.1 點擊 Resume 按鈕（最多 5 次）
      │       ├─ 出現 routenotfound → 已到目的地 → 打開地圖
      │       ├─ 畫面有變化 → 還在路上 → StateMoving_CheckFrozen()
      │       └─ 點了 5 次無反應
      │             ├─ 目標是樓梯 → 判定換樓成功 → 彈出目標
      │             └─ 目標非樓梯 → 執行 gohome
      │
      └─ 3.4 樓梯換樓成功判定
              → 彈出當前樓梯目標 → 打開地圖 → 繼續下一個目標
```

## Gohome 狀態追蹤

當執行 gohome 時設置 `_GOHOME_IN_PROGRESS = True`。戰鬥/寶箱結束後會檢查此標記繼續回城。

## 樓梯換樓判定邏輯

**Resume 失效 = 換樓成功**（因為路徑失效代表已經不在同一層）

適用的目標類型：所有以 `stair` 開頭的目標。

## 關鍵參數

| 參數 | 值 | 說明 |
|------|-----|------|
| `MAX_RESUME_DETECT_RETRIES` | 3 | Resume 按鈕檢測最大重試次數 |
| `MAX_RESUME_RETRIES` | 5 | Resume 按鈕點擊最大次數 |
| 靜止判定閾值 | 0.02 | 畫面差異 < 0.02 視為靜止 |

## RuntimeContext 變數

| 變數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `_FIRST_DUNGEON_ENTRY` | bool | True | 第一次進入地城標誌 |
| `_GOHOME_IN_PROGRESS` | bool | False | 正在回城標誌 |
| `_RESTART_OPEN_MAP_PENDING` | bool | False | 重啟後待打開地圖標誌 |

## 重啟後 / 返回後行為

### 重啟後（控制項：「重啟後首戰使用強力技能」）

**觸發條件**：遊戲重啟（`restartGame()` 被調用）

當 `_RESTART_OPEN_MAP_PENDING = True` 時：
1. **跳過 Resume 優化**：直接嘗試打開地圖
2. **前兩次戰鬥**（`_FIRST_COMBAT_AFTER_RESTART > 0`）：強制使用強力單體技能

### 返回後（控制項：「返回後首戰使用強力技能」）

當從村庄返回地城後（`_FIRST_COMBAT_AFTER_INN = True`）：
1. **第一次戰鬥**：強制使用強力單體技能

### 相關變數

| 變數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `_RESTART_OPEN_MAP_PENDING` | bool | False | 重啟後待打開地圖標誌 |
| `_FORCE_PHYSICAL_FIRST_COMBAT` | bool | True | 重啟後首戰使用強力技能 |
| `_FORCE_PHYSICAL_AFTER_INN` | bool | True | 返回後首戰使用強力技能 |
| `_FIRST_COMBAT_AFTER_RESTART` | int | 2 | 重啟後戰鬥計數器（倒數） |
| `_FIRST_COMBAT_AFTER_INN` | bool | False | 返回後第一次戰鬥標誌 |

## GUI 控制

**設定**: "啟用Resume按鈕優化(減少地圖操作)"

| 設定 | 效果 |
|------|------|
| ✅ 啟用 | 使用 Resume + routenotfound 檢測邏輯 |
| ❌ 停用 | 直接打開地圖（原始邏輯） |

## 依賴圖片資源

- `resume.png` - Resume 按鈕
- `routenotfound.png` - 路徑無效提示
- `visibliityistoopoor.png` - 能見度差提示
- `gohome.png` - 回家按鈕
