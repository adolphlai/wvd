---
name: Resume 按鈕檢測邏輯
description: 說明 Resume 按鈕優化與 routenotfound 檢測邏輯，包含樓梯換樓判定、gohome 狀態追蹤、重啟後行為。當使用者詢問 Resume 優化、StateDungeon、StateMoving_CheckFrozen 或移動卡住問題時，應啟用此技能。
---

# Resume + routenotfound 檢測邏輯

## 執行環境
- **檔案**: `src/script.py`
- **函數**: `StateDungeon()` 和 `StateMoving_CheckFrozen()`
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
│     │
│     ├─ 成功打開地圖 → 繼續任務
│     ├─ 能見度差 (visibliityistoopoor) → 執行 gohome
│     └─ 其他情況 → 重新檢測狀態
│
├─ 3. minimap_stair 恢復監控 (_MINIMAP_STAIR_IN_PROGRESS = True)
│     → 檢測 Resume 按鈕並繼續移動
│     → 監控小地圖樓層標識
│     → 完成後彈出目標
│
└─ 4. Resume 優化 (非第一次進入且非重啟後)
      │
      ├─ 4.0 先檢測特殊狀態
      │       ├─ 已在地圖狀態 (mapFlag) → 跳過
      │       ├─ 檢測到寶箱 → DungeonState.Chest
      │       └─ 檢測到戰鬥 → DungeonState.Combat
      │
      ├─ 4.1 檢測 Resume 按鈕（最多重試 3 次）
      │       ├─ 檢測到 Resume → 進入 4.2
      │       └─ 3 次都沒檢測到 → 打開地圖
      │
      ├─ 4.2 點擊 Resume 按鈕（最多 3 次）
      │       │
      │       ├─ 出現 routenotfound → 已到目的地
      │       │     ├─ 打開地圖成功 → DungeonState.Map
      │       │     └─ 能見度差 → 執行 gohome
      │       │
      │       ├─ 畫面有變化 (mean_diff >= 0.02) → 還在路上
      │       │     → 呼叫 StateMoving_CheckFrozen() 監控移動
      │       │
      │       └─ 點了 3 次畫面無變化
      │             ├─ 目標是樓梯 (stair_*) → 判定換樓成功 → 彈出目標
      │             └─ 目標非樓梯 → 執行 gohome
      │
      └─ 4.3 沒有 Resume 按鈕
              → 打開地圖
```

## StateMoving_CheckFrozen 邏輯

```
【移動監控】
│
├─ 輪詢檢查畫面變化（每 0.3 秒，最多 10 次）
│
├─ 畫面靜止 (mean_diff < 0.1) 且有 Resume 按鈕
│     → 點擊 Resume 繼續移動（最多 5 次）
│     → 5 次後仍靜止 → 執行 gohome
│
├─ 畫面靜止且 Resume 按鈕消失
│     → 已到達目標，進行狀態檢查
│
├─ 移動超時 (60 秒)
│     → 執行 gohome
│
└─ 檢測到其他狀態
      ├─ DungeonState.Map → 返回
      ├─ DungeonState.Combat → 返回
      └─ DungeonState.Chest → 返回
```

## 樓梯換樓判定邏輯

**Resume 失效 = 換樓成功**（因為路徑失效代表已經不在同一層）

適用的目標類型：所有以 `stair` 開頭的目標。

## 關鍵參數

| 參數 | 位置 | 值 | 說明 |
|------|------|-----|------|
| `MAX_RESUME_DETECT_RETRIES` | Resume優化 | 3 | Resume 按鈕檢測最大重試次數 |
| `MAX_RESUME_RETRIES` | Resume優化 | 3 | Resume 按鈕點擊最大次數 |
| `MAX_RESUME_RETRIES` | StateMoving | 5 | 畫面靜止時 Resume 點擊最大次數 |
| 變化判定閾值 | Resume優化 | 0.02 | mean_diff >= 0.02 視為有變化 |
| 靜止判定閾值 | StateMoving | 0.1 | mean_diff < 0.1 視為靜止 |
| `MOVING_TIMEOUT` | StateMoving | 60秒 | 移動超時時間 |
| `POLL_INTERVAL` | StateMoving | 0.3秒 | 輪詢間隔 |
| `MAX_POLL_COUNT` | StateMoving | 10 | 最大輪詢次數 |

## RuntimeContext 變數

| 變數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `_FIRST_DUNGEON_ENTRY` | bool | True | 第一次進入地城標誌 |
| `_GOHOME_IN_PROGRESS` | bool | False | 正在回城標誌 |
| `_RESTART_OPEN_MAP_PENDING` | bool | False | 重啟後待打開地圖標誌 |
| `_STEPAFTERRESTART` | bool | False | 重啟後左右平移標誌 |
| `_MINIMAP_STAIR_FLOOR_TARGET` | str/None | None | minimap_stair 目標樓層圖片 |
| `_MINIMAP_STAIR_IN_PROGRESS` | bool | False | minimap_stair 移動中標記 |
| `_FIRST_COMBAT_AFTER_RESTART` | int | 0 | 重啟後戰鬥計數器（倒數，重啟時設為2） |
| `_FIRST_COMBAT_AFTER_INN` | int | 0 | 返回後戰鬥計數器 |
| `_FORCE_PHYSICAL_CURRENT_COMBAT` | bool | False | 當前戰鬥強制使用強力技能 |

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
- `mapFlag.png` - 地圖標識
- `chestFlag.png` / `whowillopenit.png` - 寶箱標識
- `combatActive.png` / `combatActive_2.png` - 戰鬥標識
